import base64
import io
import json
from pathlib import Path
import sqlite3
import sys
import unittest
import uuid
import zipfile
from xml.sax.saxutils import escape

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'production'))
import recipe_import
import operations
import server as production


def odt(name,paragraphs):
 xml='<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="'+recipe_import.TEXT+'"><office:body><office:text>'
 for heading,text in paragraphs:
  tag='h' if heading else 'p';xml+='<text:'+tag+'>'+escape(text)+'</text:'+tag+'>'
 xml+='</office:text></office:body></office:document-content>'
 buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('content.xml',xml)
 return {'name':name,'data':base64.b64encode(buffer.getvalue()).decode()}


class RecipeImportTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
  self.c.executescript((Path(production.ROOT)/'schema.sql').read_text())
  self.document=odt('peanuts.odt',[(True,'SECTION 1 — Classics'),(True,'Fictional savory recipe'),(False,'Ingredients (10 lb batch)'),(False,'10 lb roasted peanuts'),(False,'2 oz salt'),(False,'1–2 oz seasoning'),(False,'Preparation:'),(False,'Cool fully.'),(True,'SECTION 2 — Process notes'),(False,'Keep original process notes.')])
 def tearDown(self):self.c.close()
 def test_category_import_keeps_original_ranges_and_creates_no_stock_or_value(self):
  result=production.apply(self.c,'import_recipes',{'documents':[self.document],'actor':'fixture-owner'},str(uuid.uuid4()))
  self.assertEqual(result['recipes'],1);self.assertEqual(result['materials'],2)
  recipe=json.loads(self.c.execute('SELECT data FROM records WHERE kind="recipes"').fetchone()[0])
  self.assertEqual(recipe['category'],'Peanuts');self.assertEqual(recipe['subcategory'],'Classics')
  self.assertEqual(recipe['status'],'Draft');self.assertIsNone(recipe['expected_yield'])
  self.assertIn('1–2 oz seasoning',recipe['unresolved_ingredients'])
  self.assertIn('Cool fully.',recipe['source_variants'][0]['text'])
  self.assertEqual(self.c.execute('SELECT count(*) FROM lots').fetchone()[0],0)
  self.assertEqual(self.c.execute('SELECT count(*) FROM movements').fetchone()[0],0)
  for row in self.c.execute('SELECT data FROM records WHERE kind="materials"'):
   material=json.loads(row[0]);self.assertEqual(material['quantity'],0);self.assertEqual(material['cost'],0)
  event=json.loads(self.c.execute('SELECT data FROM events').fetchone()[0]);self.assertEqual(event['documents'],1);self.assertNotIn('data',json.dumps(event))
 def test_same_event_and_same_file_import_are_both_idempotent(self):
  event=str(uuid.uuid4())
  production.apply(self.c,'import_recipes',{'documents':[self.document]},event)
  again=production.apply(self.c,'import_recipes',{'documents':[self.document]},event)
  self.assertTrue(again['duplicate'])
  again=production.apply(self.c,'import_recipes',{'documents':[self.document]},str(uuid.uuid4()))
  self.assertEqual(again['recipes'],0);self.assertEqual(again['skipped'],1);self.assertEqual(again['materials'],0)
  self.assertEqual(self.c.execute('SELECT count(*) FROM records WHERE kind="recipe_documents"').fetchone()[0],1)
 def test_approval_requires_reviewed_valid_formula_and_preserves_source_when_editing(self):
  production.apply(self.c,'import_recipes',{'documents':[self.document]},str(uuid.uuid4()))
  row=self.c.execute('SELECT id,data FROM records WHERE kind="recipes"').fetchone();recipe=json.loads(row['data'])
  with self.assertRaisesRegex(ValueError,'Review and save'):operations.apply(self.c,'approve_recipe',{'id':row['id']},str(uuid.uuid4()))
  edited={**recipe,'id':row['id'],'batch_size':10.125,'expected_yield':10,'confirm_imported_formula':True,'instructions':'Reviewed manufacturing instructions'}
  operations.apply(self.c,'recipe_versions',edited,str(uuid.uuid4()))
  operations.apply(self.c,'approve_recipe',{'id':row['id']},str(uuid.uuid4()))
  current=operations.get(self.c,row['id'],'recipes')
  self.assertEqual(current['status'],'Approved');self.assertEqual(current['source_variants'],recipe['source_variants'])
  self.assertEqual(current['category'],'Peanuts')
 def test_duplicate_formula_versions_merge_without_doubling_ingredients(self):
  doc=odt('coffee.odt',[(False,'Fictional roast'),(False,'Origin: Test region'),(False,'Roast profile one'),(False,'Winter'),(False,'Fictional roast'),(False,'Origin: Test region'),(False,'Roast profile two')])
  parsed=recipe_import.preview([doc]);self.assertEqual(len(parsed['recipes']),1)
  self.assertEqual(len(parsed['recipes'][0]['variants']),2)
  self.assertIn('Winter',parsed['recipes'][0]['subcategories'])
 def test_incomplete_volume_recipes_remain_available_as_drafts_and_source_notes(self):
  docs=[odt('pickels.odt',[(False,'Fictional pickles'),(False,'Ingredients:'),(False,'1 cup water'),(False,'Method:'),(False,'Use the source procedure.')]),odt('icecream.odt',[(True,'1. ? Fictional frozen dessert'),(False,'Start with the vanilla base.'),(False,'Add:'),(False,'200–300 g inclusions')])]
  parsed=recipe_import.preview(docs);self.assertEqual(parsed['categories']['Pickles'],1);self.assertEqual(parsed['categories']['Ice Cream'],1)
  for doc in docs:production.apply(self.c,'import_recipes',{'documents':[doc]},str(uuid.uuid4()))
  for row in self.c.execute('SELECT data FROM records WHERE kind="recipes"'):
   value=json.loads(row['data']);self.assertEqual(value['status'],'Draft');self.assertTrue(value['source_variants'])
 def test_malformed_files_and_external_xml_entities_are_rejected(self):
  for item in [{'name':'../peanuts.odt','data':'AA=='},{'name':'peanuts.odt','data':'bad'},odt('unknown.odt',[(False,'data')])]:
   with self.assertRaises(ValueError):recipe_import.preview([item])
  stream=io.BytesIO()
  with zipfile.ZipFile(stream,'w') as z:z.writestr('content.xml','<!DOCTYPE x [<!ENTITY private SYSTEM "file:///private">]><x/>')
  with self.assertRaisesRegex(ValueError,'External XML'):recipe_import.preview([{'name':'peanuts.odt','data':base64.b64encode(stream.getvalue()).decode()}])


if __name__=='__main__':unittest.main()
