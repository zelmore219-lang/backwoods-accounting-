"""Local ODT recipe library import. Source documents never need a cloud upload."""
import base64
import hashlib
import io
import json
import re
import unicodedata
import uuid
import xml.etree.ElementTree as ET
import zipfile
import operations

TEXT='urn:oasis:names:tc:opendocument:xmlns:text:1.0'
CATEGORIES=('Peanuts','Coffee','Ice Cream','Pickles')
LIMIT=2*1024*1024


def clean(value):
 return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value))).strip()


def key(value):
 return re.sub(r'[^\w]+',' ',clean(value).casefold()).strip()


def category_for(filename):
 value=key(filename)
 for needles,category in [(('peanut',),'Peanuts'),(('coffee',),'Coffee'),(('icecream','ice cream'),'Ice Cream'),(('pickle','pickel'),'Pickles')]:
  if any(n in value for n in needles):return category
 raise ValueError('Choose a document named for Peanuts, Coffee, Ice Cream or Pickles')


def node_text(node):
 result=node.text or ''
 for child in node:
  if child.tag=='{'+TEXT+'}line-break':result+='\n'
  elif child.tag=='{'+TEXT+'}tab':result+='\t'
  elif child.tag=='{'+TEXT+'}s':result+=' '*min(100,int(child.get('{'+TEXT+'}c','1')))
  else:result+=node_text(child)
  result+=child.tail or ''
 return result.strip()


def read_document(item):
 name=str(item.get('name',''))
 if not name.lower().endswith('.odt') or '/' in name or '\\' in name:raise ValueError('Choose an OpenDocument .odt recipe file')
 category=category_for(name)
 try:raw=base64.b64decode(item.get('data',''),validate=True)
 except (ValueError,TypeError):raise ValueError('The recipe document could not be read')
 if not raw or len(raw)>LIMIT:raise ValueError('Each recipe document must be no larger than 2 MB')
 try:
  with zipfile.ZipFile(io.BytesIO(raw)) as archive:
   info=archive.getinfo('content.xml')
   if info.file_size>4*LIMIT:raise ValueError('The expanded recipe document is too large')
   xml=archive.read(info)
  if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():raise ValueError('External XML declarations are not supported')
  root=ET.fromstring(xml)
 except (zipfile.BadZipFile,KeyError,ET.ParseError):raise ValueError('This file is not a readable ODT document')
 paragraphs=[]
 for node in root.iter():
  if node.tag in {'{'+TEXT+'}p','{'+TEXT+'}h'}:
   text=node_text(node)
   if text:paragraphs.append({'text':text,'heading':node.tag.endswith('}h')})
 if not paragraphs:raise ValueError('The recipe document has no text')
 return {'name':name,'category':category,'sha256':hashlib.sha256(raw).hexdigest(),'paragraphs':paragraphs}


def title(value):
 value=re.sub(r'^\s*\d+[.)]\s*','',value)
 # Remove leading numbering, emoji and broken emoji encoding in English titles.
 return re.sub(r'^[^A-Za-z0-9]+(?=[A-Za-z0-9])','',value).strip()


def sections(document):
 rows=document['paragraphs'];category=document['category'];starts=[];group='Core range'
 for i,row in enumerate(rows):
  text=row['text'];next_text=rows[i+1]['text'] if i+1<len(rows) else ''
  if re.search(r'\bSECTION\s+\d+\b',text,re.I):
   group=re.sub(r'^.*?SECTION\s+\d+\s*[—–:-]?\s*','',text,flags=re.I);continue
  if category=='Coffee' and re.fullmatch(r'(Spring|Summer|Fall|Winter)(?: Lineup)?',text,re.I):group=text.replace(' Lineup','');continue
  if category=='Coffee':is_title=next_text.startswith('Origin:')
  elif category=='Pickles':is_title=next_text.casefold().startswith('ingredients')
  elif category=='Ice Cream':is_title=row['heading']
  else:
   # Peanuts recipes are document headings followed by their formula/profile.
   stop=next((j for j in range(i+1,len(rows)) if rows[j]['heading']),len(rows))
   is_title=row['heading'] and any('ingredients' in x['text'].casefold() for x in rows[i+1:stop])
  if is_title:starts.append((i,title(text),group))
 result=[]
 for n,(start,name,subgroup) in enumerate(starts):
  end=starts[n+1][0] if n+1<len(starts) else len(rows)
  if category=='Peanuts':
   end=next((j for j in range(start+1,end) if rows[j]['heading']),end)
  elif category=='Pickles':
   end=next((j for j in range(start+1,end) if rows[j]['heading']),end)
  body=[x['text'] for x in rows[start+1:end] if not re.fullmatch(r'(Spring|Summer|Fall|Winter)(?: Lineup)?',x['text'],re.I)]
  result.append({'name':name,'category':category,'subcategory':subgroup,'body':body,'paragraph':start+1})
 return result


def preview(items):
 if not isinstance(items,list) or not 1<=len(items)<=8:raise ValueError('Select between one and eight recipe documents')
 documents=[read_document(item) for item in items];recipes={}
 for document in documents:
  for section in sections(document):
   identity=(section['category'],key(section['name']))
   recipe=recipes.setdefault(identity,{'name':section['name'],'category':section['category'],'subcategories':[],'variants':[]})
   if section['subcategory'] not in recipe['subcategories']:recipe['subcategories'].append(section['subcategory'])
   variant={'document':document['name'],'document_sha256':document['sha256'],'paragraph':section['paragraph'],'text':'\n'.join(section['body'])}
   if not any(v['text']==variant['text'] for v in recipe['variants']):recipe['variants'].append(variant)
 return {'documents':documents,'recipes':list(recipes.values()),'categories':{c:sum(r['category']==c for r in recipes.values()) for c in CATEGORIES}}


def ingredients(variant):
 body=variant['text'].splitlines();selected=[];active=False
 for line in body:
  if line.casefold().startswith(('ingredients','add:','add to the mix:','then add:')):active=True;continue
  if re.match(r'^(Method|Preparation|Roast Method|Tip)\s*:',line,re.I) or line.casefold()=='method':active=False
  if active:selected.append(line)
 return selected


def apply(c,data):
 parsed=preview(data.get('documents'));counts={'recipes':0,'documents':0,'skipped':0,'materials':0}
 existing={}
 for row in c.execute('SELECT id,data FROM records WHERE kind="recipes"'):
  value=json.loads(row['data'])
  existing[(value.get('category',''),key(value.get('name','')))]=(row['id'],value)
 documents={json.loads(r['data']).get('sha256') for r in c.execute('SELECT data FROM records WHERE kind="recipe_documents"')}
 for document in parsed['documents']:
  if document['sha256'] not in documents:
   operations.save(c,'recipe_documents',document);documents.add(document['sha256']);counts['documents']+=1
 for item in parsed['recipes']:
  identity=(item['category'],key(item['name']))
  if identity in existing:
   ident,value=existing[identity]
   if not value.get('imported_recipe'):counts['skipped']+=1;continue
   if value.get('status')!='Draft':counts['skipped']+=1;continue
   variants=value.get('source_variants',[])
   new=[v for v in item['variants'] if not any(old.get('document_sha256')==v['document_sha256'] and old.get('text')==v['text'] for old in variants)]
   if not new:counts['skipped']+=1;continue
   # Revised documents are supporting versions, never edits to an approved BOM.
   value['source_variants']=[*variants,*new];operations.update(c,ident,value);continue
  lines=[];unresolved=[];source_lines=ingredients(item['variants'][0])
  for line in source_lines:
   match=re.fullmatch(r'(\d[\d,]*(?:\.\d+)?)\s*(lb|oz|g|kg)\s+(.+)',line,re.I)
   if not match:unresolved.append(line);continue
   quantity=float(match[1].replace(',',''));unit=match[2].lower();name=match[3].strip()
   if not quantity:unresolved.append(line);continue
   matches=[]
   for row in c.execute('SELECT id,data FROM records WHERE kind="materials"'):
    material=json.loads(row['data'])
    if key(material.get('name',''))==key(name) and material.get('unit') in {'lb','oz','g','kg'}:matches.append(row['id'])
   if len(matches)==1:material=matches[0]
   elif len(matches)>1:
    unresolved.append(line+' — multiple existing material matches; choose one when reviewing the draft')
    continue
   else:
    material=operations.save(c,'materials',{'name':name,'unit':unit,'quantity':0,'cost':0,'reorder':0,'category':item['category'],'imported_recipe_material':True})
    counts['materials']+=1
   lines.append({'material':material,'quantity':quantity,'unit':unit})
  text='\n\n'.join(v['text'] for v in item['variants'])
  size=re.search(r'\b(\d+(?:\.\d+)?)\s*lb\s+batch\b',text,re.I)
  issues=['Confirm the finished batch yield in pounds and the package size before approval.','Review ingredient mappings, quantities, referenced base formulas and production instructions.']
  if unresolved:issues.append('Some source ingredients have ranges, volume units or missing quantities; enter confirmed BOM quantities.')
  if len(item['variants'])>1:issues.append('The document contains repeated source versions. Review all versions before approving one formula.')
  value={'name':item['name'],'version':'Imported draft','category':item['category'],'subcategory':', '.join(item['subcategories']),'status':'Draft','batch_size':float(size[1]) if size else None,'expected_yield':None,'lines':lines,'instructions':text,'imported_recipe':True,'source_variants':item['variants'],'source_ingredients':source_lines,'unresolved_ingredients':unresolved,'review_issues':issues}
  ident=operations.save(c,'recipes',value);existing[identity]=(ident,value);counts['recipes']+=1
 # Audit the import identities and counts, not duplicate copies of file bytes.
 actor=data.get('actor');data.clear();data.update({'actor':actor,'sources':[{'name':d['name'],'sha256':d['sha256']} for d in parsed['documents']],**counts})
 return {'ok':True,**counts,'categories':parsed['categories']}
