"""Validated standalone production operations. All writes share the caller transaction."""
import json,uuid,math
FACTORS={'lb':1,'oz':1/16,'g':1/453.59237,'kg':1000/453.59237,'each':1,'bag':1,'case':1}
def number(v,positive=False):
 n=float(v)
 if not math.isfinite(n) or n<0 or (positive and n<=0):raise ValueError('Enter a finite positive quantity or cost')
 return n
def convert(q,source,target):
 if source not in FACTORS or target not in FACTORS:raise ValueError('Unsupported unit')
 if (source in ('each','bag','case') or target in ('each','bag','case')) and source!=target:raise ValueError('Count conversions require explicit pack size')
 return number(q)*FACTORS[source]/FACTORS[target]
def save(c,kind,data,id=None):
 id=id or str(uuid.uuid4());c.execute('insert into records values(?,?,?)',(id,kind,json.dumps(data)));return id
def get(c,id,kind=None):
 r=c.execute('select * from records where id=?',(id,)).fetchone()
 if not r or (kind and r['kind']!=kind):raise ValueError('Referenced record not found')
 return json.loads(r['data'])
def update(c,id,d):c.execute('update records set data=? where id=?',(json.dumps(d),id))
def revalue(c,id):
 m=get(c,id,'materials');row=c.execute('select coalesce(sum(quantity),0),coalesce(sum(quantity*cost),0) from lots where material=?',(id,)).fetchone()
 m['quantity']=row[0]
 if row[0]>0:m['cost']=row[1]/row[0]
 update(c,id,m)
def move(c,material,qty,lot,event):
 m=get(c,material,'materials');q=float(m['quantity'])+qty
 if q < -0.0000001:raise ValueError('Insufficient stock')
 m['quantity']=max(0,q);update(c,material,m)
 if qty>0:c.execute('insert into lots(id,material,source_lot,quantity,cost) values(?,?,?,?,?)',(str(uuid.uuid4()),material,lot,qty,m['cost']))
 else:
  need=-qty
  for r in c.execute('select * from lots where material=? and quantity>0 order by rowid',(material,)).fetchall():
   take=min(need,r['quantity']);c.execute('update lots set quantity=quantity-? where id=?',(take,r['id']));need-=take
   if need<1e-8:break
 revalue(c,material)
 c.execute('insert into movements values(?,?,?,?,?,datetime("now"))',(str(uuid.uuid4()),material,qty,lot,event))
def save_schedule(c, data):
 from datetime import date, time

 entry_id = data.get('id')
 if entry_id:
  if get(c, entry_id, 'production_schedule')['status'] != 'Planned':
   raise ValueError('Only planned runs can be edited')
 product = data.get('product', '').strip()
 quantity = number(data.get('batch_count'), True)
 if quantity != int(quantity):
  raise ValueError('Enter a whole number of batches')
 status = data.get('status', 'Planned')
 if status not in ('Planned', 'Completed', 'Cancelled'):
  raise ValueError('Invalid schedule status')
 start_time = data.get('start_time', '')
 recipe_id = data.get('recipe', '')
 if status == 'Planned' and not recipe_id:
  raise ValueError('Select an approved recipe for a planned run')
 recipe_label = ''
 if recipe_id:
  recipe = get(c, recipe_id, 'recipes')
  if recipe.get('status') != 'Approved':
   raise ValueError('Select an approved recipe')
  recipe_label = f"{recipe['name']} / version {recipe['version']}"
  product = product or recipe['name']
 if not product:
  raise ValueError('Enter a product or production task')
 entry = dict(
  product=product, date=date.fromisoformat(data['date']).isoformat(),
  start_time=time.fromisoformat(start_time).strftime('%H:%M') if start_time else '',
  batch_count=int(quantity), recipe=recipe_id, recipe_label=recipe_label,
  status=status, notes=data.get('notes', '').strip(),
  planned_extra_cost=number(data.get('planned_extra_cost') or 0)
 )
 if entry_id:
  update(c, entry_id, entry)
 else:
  save(c, 'production_schedule', entry)

def schedule_requirements(c, entry_id, show_cost):
 from datetime import date

 entry = get(c, entry_id, 'production_schedule')
 if not entry.get('recipe'):
  return {'lines': [], 'has_recipe': False}
 recipe = get(c, entry['recipe'], 'recipes')
 required = {}
 for line in recipe['lines']:
  material_id = line['material']
  material = get(c, material_id, 'materials')
  unit = material.get('unit', 'lb')
  quantity = convert(line['quantity'], line['unit'], unit) * entry['batch_count']
  required[material_id] = required.get(material_id, 0) + quantity

 lines = []
 stock_date = max(entry['date'], date.today().isoformat())
 total = 0
 for material_id, quantity in required.items():
  material = get(c, material_id, 'materials')
  available = c.execute(
   """SELECT COALESCE(SUM(quantity), 0) FROM lots
      WHERE material=? AND status='Approved' AND quantity>0
      AND (expires IS NULL OR expires='' OR expires>=?)""",
   (material_id, stock_date)
  ).fetchone()[0]
  item = dict(name=material['name'], unit=material.get('unit', 'lb'),
              required=quantity, available=available, shortage=max(0, quantity-available))
  if show_cost:
   item['estimated_cost'] = quantity * float(material.get('cost', 0))
   total += item['estimated_cost']
  lines.append(item)
 result = dict(lines=lines, has_recipe=True,
               expected_yield=float(recipe['expected_yield']) * entry['batch_count'])
 if show_cost:
  result['estimated_material_cost'] = total
  result['planned_extra_cost'] = entry.get('planned_extra_cost', 0)
  result['estimated_total_cost'] = total + result['planned_extra_cost']
 return result

def available_finished_units(batch):
 return (float(batch['packages']) - float(batch.get('reserved', 0))
         - float(batch.get('delivered', 0)) - float(batch.get('written_off', 0))
         + float(batch.get('returned', 0)) - float(batch.get('converted_units', 0)) - float(batch.get('vendor_transferred', 0)))

def consume_material(c, material_id, quantity, finished_lot, event):
 material = get(c, material_id, 'materials')
 remaining = quantity
 allocations = []
 for lot in c.execute(
  """SELECT * FROM lots WHERE material=? AND quantity>0 AND status='Approved'
     AND (expires IS NULL OR expires='' OR expires>=date('now')) ORDER BY rowid""",
  (material_id,)
 ).fetchall():
  take = min(remaining, lot['quantity'])
  allocations.append(dict(lot_id=lot['id'], source_lot=lot['source_lot'],
                          supplier=lot['supplier'], quantity=take, cost=take*lot['cost']))
  remaining -= take
  if remaining < 1e-8:
   break
 if remaining > 1e-8:
  raise ValueError('Insufficient approved, unexpired lot stock for ' + material['name'])
 for allocation in allocations:
  c.execute('UPDATE lots SET quantity=quantity-? WHERE id=?',
            (allocation['quantity'], allocation['lot_id']))
 revalue(c, material_id)
 c.execute('INSERT INTO movements VALUES(?,?,?,?,?,datetime("now"))',
           (str(uuid.uuid4()), material_id, -quantity, finished_lot, event))
 return dict(material=material_id, name=material['name'], unit=material.get('unit', 'lb'),
             quantity=quantity, cost=sum(item['cost'] for item in allocations), lots=allocations)

def batch_cost_lines(c, batch):
 if 'cost_lines' in batch:
  return batch['cost_lines']
 lines = []
 for item in batch.get('inputs', []):
  material = get(c, item['material'], 'materials')
  lines.append(dict(name=item.get('name', material['name']), quantity=item['quantity'],
                    unit=item.get('unit', material.get('unit', 'lb')), cost=item['cost']))
 for key, label in [('labor', 'Labor'), ('energy', 'Energy'), ('overhead', 'Overhead'),
                    ('other', 'Other production costs'), ('packaging_cost', 'Additional packaging costs')]:
  if batch.get(key):
   lines.append(dict(name=label, cost=float(batch[key])))
 remaining = float(batch.get('total', 0)) - sum(line['cost'] for line in lines)
 if abs(remaining) > 1e-7:
  lines.append(dict(name='Other recorded batch costs', cost=remaining))
 return lines

def package_inventory(c, data, event):
 from datetime import date

 source_id = data['batch']
 source = get(c, source_id, 'batches')
 if source['status'] not in ('Approved', 'Released for sale'):
  raise ValueError('Source inventory must pass inspection before packaging')
 if source.get('best_by') and source['best_by'] < date.today().isoformat():
  raise ValueError('Source inventory has expired')
 count = number(data['packages'], True)
 if count != int(count):
  raise ValueError('Enter a whole number of finished packages')
 weight = number(data['weight_per_package'], True) * count
 weight_per_source_unit = number(source['output'], True) / number(source['packages'], True)
 source_units = weight / weight_per_source_unit
 if not source.get('bulk'):
  whole_units = round(source_units)
  if whole_units < 1 or not math.isclose(source_units, whole_units, rel_tol=0, abs_tol=1e-8):
   raise ValueError('Repackaging must use whole source packages. Record unpackaged batches as bulk to package partial weights.')
  source_units = whole_units
  weight = source_units * weight_per_source_unit
 available = available_finished_units(source)
 if available <= 0 or source_units > available + 1e-10:
  raise ValueError(f'Insufficient unreserved source inventory: {weight:.6g} lb needed, '
                   f'{max(0, available) * weight_per_source_unit:.6g} lb available.')
 source_units = min(source_units, available)
 weight = source_units * weight_per_source_unit
 lot, sku = data['lot'].strip(), data['sku'].strip()
 if not lot or not sku:
  raise ValueError('Enter the packaged SKU and a new lot number')
 if c.execute("SELECT 1 FROM records WHERE kind='batches' AND json_extract(data,'$.lot')=?", (lot,)).fetchone():
  raise ValueError('That finished lot number is already in use')
 added_cost = number(data.get('packaging_cost') or 0)
 packaging_labor = number(data.get('labor') or 0)
 fraction = source_units / float(source['packages'])
 lines = []
 for source_line in batch_cost_lines(c, source):
  line = dict(source_line, cost=source_line['cost'] * fraction)
  if 'quantity' in line:
   line['quantity'] *= fraction
  lines.append(line)
 inputs = []
 if data.get('packaging_material'):
  material_id = data['packaging_material']
  if get(c, material_id, 'materials').get('unit') not in ('each', 'bag'):
   raise ValueError('Choose packaging stocked by each or bag')
  item = consume_material(c, material_id, count, lot, event)
  inputs.append(item)
  lines.append({key: item[key] for key in ('name', 'quantity', 'unit', 'cost')})
 if packaging_labor:
  lines.append(dict(name='Packaging labor', cost=packaging_labor))
 if added_cost:
  lines.append(dict(name='Additional packaging costs', cost=added_cost))
 total = sum(line['cost'] for line in lines)
 packaged = dict(
  name=source['name'], sku=sku, lot=lot, output=weight, packages=int(count),
  status='Awaiting inspection', best_by=source.get('best_by', ''),
  date=date.today().isoformat(), source_batch=source_id, source_lot=source['lot'], loss=0,
  recipe=source.get('recipe'), recipe_snapshot=source.get('recipe_snapshot'),
  total=total, unit=total/count, per_lb=total/weight, packaging_cost=added_cost,
  inputs=inputs, cost_lines=lines, labor=packaging_labor,
  reserved=0, delivered=0, returned=0, written_off=0
 )
 source['converted_units'] = float(source.get('converted_units', 0)) + source_units
 update(c, source_id, source)
 return save(c, 'batches', packaged)

def correct_lot_cost(c, data):
 lot = c.execute('SELECT * FROM lots WHERE id=?', (data['id'],)).fetchone()
 if lot is None:
  raise ValueError('Material lot not found')
 new_cost = number(data['cost'])
 if not data.get('reason', '').strip():
  raise ValueError('Enter the reason for this cost correction')
 changes = {}
 for row in c.execute("SELECT id, data FROM records WHERE kind='batches' ORDER BY rowid").fetchall():
  batch = json.loads(row['data'])
  parent_change = changes.get(batch.get('source_batch'))
  previous_lines = [dict(line) for line in batch_cost_lines(c, batch)]
  input_deltas = []
  for item in batch.get('inputs', []):
   delta = 0
   for allocation in item.get('lots', []):
    if allocation['lot_id'] == lot['id']:
     corrected = allocation['quantity'] * new_cost
     delta += corrected - allocation['cost']
     allocation['cost'] = corrected
   if delta:
    item['cost'] += delta
    input_deltas.append((item, delta))
  if not parent_change and not input_deltas:
   continue
  if (batch['status'] not in ('In Production', 'Awaiting inspection', 'Approved')
      or any(batch.get(key, 0) for key in ('reserved', 'delivered', 'returned', 'written_off'))
      or c.execute(
   """SELECT 1 FROM events WHERE kind='quality' AND json_extract(data,'$.id')=?
      AND json_extract(data,'$.status')='Released for sale'""", (row['id'],)
  ).fetchone()):
   raise ValueError('This lot feeds a finalized batch. Its cost cannot be changed here.')
  direct_delta = sum(delta for _, delta in input_deltas)
  carried_delta = 0
  if batch.get('source_batch'):
   if 'cost_lines' not in batch:
    raise ValueError('The packaged batch has no detailed cost history for this correction')
   if parent_change:
    old_parent, new_parent = parent_change
    fraction = batch['output'] / new_parent['output']
    inherited = []
    for line in batch_cost_lines(c, new_parent):
     carried = dict(line, cost=line['cost'] * fraction)
     if 'quantity' in carried:
      carried['quantity'] *= fraction
     inherited.append(carried)
    lines = inherited + batch['cost_lines'][len(old_parent):]
    carried_delta = (new_parent['total'] - sum(line['cost'] for line in old_parent)) * fraction
   else:
    lines = batch['cost_lines']
   for item, delta in input_deltas:
    for line in reversed(lines):
     if line.get('name') == item['name'] and line.get('quantity') == item['quantity']:
      line['cost'] += delta
      break
    else:
     raise ValueError('The packaged batch has no matching cost line for this material')
   batch['cost_lines'] = lines
  batch['total'] += direct_delta + carried_delta
  if 'material_variance' in batch:
   batch['material_variance'] += direct_delta
  batch['per_lb'] = batch['total'] / batch['output']
  batch['unit'] = batch['total'] / batch['packages'] if batch['packages'] else 0
  changes[row['id']] = (previous_lines, batch)
 for batch_id, (_, batch) in changes.items():
  update(c, batch_id, batch)
 c.execute('UPDATE lots SET cost=? WHERE id=?', (new_cost, lot['id']))
 revalue(c, lot['material'])
 data.update(previous_unit_cost=lot['cost'], affected_batches=list(changes))

def apply(c,k,d,event):
 if k=='save_schedule':
  save_schedule(c,d)
 elif k=='correct_lot_cost':
  correct_lot_cost(c,d)
 elif k=='package_inventory':
  d['packaged_batch']=package_inventory(c,d,event)
 elif k=='start_batch':
  schedule_id=d.get('schedule_id')
  if schedule_id:
   run=get(c,schedule_id,'production_schedule')
   if run['status']!='Planned' or not run.get('recipe'):
    raise ValueError('Select a planned run with an approved recipe')
   d.update(recipe=run['recipe'],scale=run['batch_count'])
  r=get(c,d['recipe'],'recipes');scale=number(d['scale'],True)
  staged=dict(d,output=float(r['expected_yield'])*scale,packages=1,labor=0,energy=0,overhead=0,other=0)
  apply(c,'manufacture',staged,event)
  row=c.execute('select id,data from records where kind="batches" order by rowid desc limit 1').fetchone();batch=json.loads(row['data']);batch['status']='In Production';batch['packages']=0;batch['unit']=0;batch['stage']='Roasting';update(c,row['id'],batch)
  if schedule_id:
   run.update(status='In Production',batch=row['id'])
   update(c,schedule_id,run)
 elif k in ('complete_batch','edit_batch'):
  b=get(c,d['id'],'batches')
  if k=='complete_batch' and b['status']!='In Production':raise ValueError('Batch is not in production')
  if k=='edit_batch' and (b['status']!='Awaiting inspection' or b.get('source_batch')):
   raise ValueError('Only production batches awaiting inspection can be edited here')
  output=number(d['output'],True);packages=1 if d.get('bulk') is True else number(d['packages'],True)
  if packages!=int(packages):raise ValueError('Enter whole package quantities')
  weight=sum(i['quantity']*FACTORS[get(c,i['material'],'materials').get('unit','lb')] for i in b['inputs'] if get(c,i['material'],'materials').get('unit','lb') in ('lb','oz','g','kg'))
  if output>weight:raise ValueError('Finished weight exceeds ingredient input')
  extras=sum(number(d.get(x,0)) for x in ('labor','energy','overhead','other'));total=sum(i['cost'] for i in b['inputs'])+extras
  b.update({key:d[key] for key in ('bulk','best_by','profile','labor','energy','overhead','other') if key in d})
  b.update(total=total,output=output,packages=int(packages),unit=total/packages,per_lb=total/output,loss=(weight-output)/weight*100,yield_variance=output-b['expected_output'],status='Awaiting inspection');update(c,d['id'],b)
  if k=='complete_batch' and b.get('schedule_id'):
   run=get(c,b['schedule_id'],'production_schedule')
   run['status']='Completed'
   update(c,b['schedule_id'],run)
 elif k=='batch_stage':
  b=get(c,d['id'],'batches')
  if b['status']!='In Production' or d['stage'] not in ('Roasting','Seasoning','Tumbling','Packaging'):raise ValueError('Invalid production stage')
  b.update(stage=d['stage'],observations=d.get('notes',''));update(c,d['id'],b)
 elif k=='writeoff':
  b=get(c,d['batch'],'batches');q=number(d['quantity'],True)
  available=available_finished_units(b)
  if b.get('bulk'):raise ValueError('Package bulk stock before recording a package write-off')
  if q>available or not d.get('notes'):raise ValueError('Available quantity and reason required')
  b['written_off']=float(b.get('written_off',0))+q;update(c,d['batch'],b);d['cost']=q*b['unit'];save(c,'writeoffs',d)
  save(c,'outbox',dict(type='inventory.waste',event_id=event,batch=d['batch'],quantity=q,cost=d['cost'],status='Pending connection'))
 elif k=='prices':
  get(c,d['supplier'],'suppliers');m=get(c,d['material'],'materials')
  q=number(d['quantity'],True);price=number(d['price']);freight=number(d.get('freight',0));d['landed']=(price*q+freight)/convert(q,d['unit'],m.get('unit','lb'))
  for row in c.execute('select data from records where kind="prices" order by rowid desc'):
   old=json.loads(row[0])
   if old['supplier']==d['supplier'] and old['material']==d['material']:
    d['previous_landed']=old['landed'];d['increase']=d['landed']-old['landed'];break
  save(c,k,d)
 elif k=='recipe_versions':
  if not d.get('name') or not d.get('version'):raise ValueError('Name and version required')
  recipe_id=d.get('id')
  prior=get(c,recipe_id,'recipes') if recipe_id else {}
  if recipe_id and prior['status']!='Draft':
   raise ValueError('Only draft recipes can be edited')
  lines=d['lines']
  for row in c.execute('select id,data from records where kind="recipes"'):
   if row['id']==recipe_id:continue
   other=json.loads(row['data'])
   if other.get('name')==d['name'] and other.get('version')==d['version']:raise ValueError('Recipe version already exists; increment the version')
  if not isinstance(lines,list) or not lines:raise ValueError('At least one BOM line required')
  for line in lines:
   m=get(c,line['material'],'materials');convert(number(line['quantity'],True),line['unit'],m.get('unit','lb'))
  number(d['batch_size'],True);number(d['expected_yield'],True);d['status']='Draft'
  if prior.get('imported_recipe'):
   d={**prior,**d,'formula_reviewed':d.get('confirm_imported_formula') is True}
  if recipe_id:update(c,recipe_id,{key:value for key,value in d.items() if key!='id'})
  else:save(c,'recipes',d)
 elif k=='edit_purchase':
  purchase=get(c,d['id'],'purchases')
  if purchase.get('status')!='Draft' or purchase.get('received',0):
   raise ValueError('Only draft purchase orders can be edited')
  if not d.get('name','').strip():raise ValueError('Enter a purchase order number')
  get(c,d['supplier'],'suppliers')
  get(c,d['material'],'materials')
  number(d['quantity'],True);number(d['cost']);number(d['freight'])
  purchase.update({key:d[key] for key in ('name','supplier','material','quantity','cost','freight')})
  update(c,d['id'],purchase)
 elif k=='approve_purchase':
  p=get(c,d['id'],'purchases')
  if p.get('status')!='Draft':raise ValueError('Only draft purchases may be approved')
  p['status']='Approved';update(c,d['id'],p)
 elif k=='approve_recipe':
  r=get(c,d['id'],'recipes')
  if r.get('status')!='Draft':raise ValueError('Only draft versions may be approved')
  if r.get('imported_recipe') and r.get('formula_reviewed') is not True:raise ValueError('Review and save the imported formula, base recipes, quantities and finished yield before approval')
  number(r.get('batch_size'),True);number(r.get('expected_yield'),True)
  if not r.get('lines'):raise ValueError('At least one confirmed ingredient is required')
  for line in r['lines']:
   m=get(c,line['material'],'materials');convert(number(line['quantity'],True),line['unit'],m.get('unit','lb'))
  r['standard_material_cost']=sum(convert(line['quantity'],line['unit'],get(c,line['material'],'materials').get('unit','lb'))*number(get(c,line['material'],'materials')['cost']) for line in r['lines']);r['status']='Approved';update(c,d['id'],r)
 elif k=='manufacture':
  r=get(c,d['recipe'],'recipes')
  if r.get('status')!='Approved':raise ValueError('Use an approved recipe version')
  scale=number(d['scale'],True);output=number(d['output'],True);packages=1 if d.get('bulk') is True else number(d['packages'],True)
  if packages!=int(packages):raise ValueError('Packages must be whole numbers')
  inputs=[];material_cost=0
  # Consolidate repeated materials before checking stock.
  combined={}
  for line in r['lines']:
   m=get(c,line['material'],'materials');q=convert(line['quantity'],line['unit'],m.get('unit','lb'))*scale
   combined[line['material']]=combined.get(line['material'],0)+q
  for id,q in combined.items():
   item = consume_material(c, id, q, d['lot'], event)
   material_cost += item['cost']
   inputs.append(item)
  extras=sum(number(d.get(x,0)) for x in ('labor','energy','overhead','other'))
  total=material_cost+extras;expected=number(r['expected_yield'],True)*scale;input_weight=sum(convert(line['quantity'],line['unit'],'lb')*scale for line in r['lines'] if line['unit'] in ('lb','oz','g','kg'))
  if output>input_weight+1e-7:raise ValueError('Usable output cannot exceed recorded ingredient input weight')
  d.update(name=r['name'],recipe_snapshot=r,inputs=inputs,total=total,unit=total/packages,per_lb=total/output,loss=(input_weight-output)/input_weight*100,expected_output=expected,yield_variance=output-expected,standard_material_cost=r.get('standard_material_cost',0)*scale,material_variance=material_cost-r.get('standard_material_cost',0)*scale,status='Awaiting inspection',reserved=0,delivered=0,returned=0,written_off=0)
  save(c,'batches',d)
 elif k=='adjust':
  amount=float(d['quantity'])
  if not math.isfinite(amount) or not amount or not d.get('reason'):raise ValueError('Quantity and reason required')
  move(c,d['material'],amount,d['lot'],event)
 elif k=='reserve':
  b=get(c,d['batch'],'batches');q=number(d['quantity'],True)
  available=available_finished_units(b)
  import datetime
  if b.get('best_by') and b['best_by']<datetime.date.today().isoformat():raise ValueError('Finished lot expired')
  if q!=int(q):raise ValueError('Reserve whole packages')
  if b.get('bulk') or b['status']!='Released for sale' or q>available:raise ValueError('Insufficient released packaged stock')
  b['reserved']=float(b.get('reserved',0))+q;update(c,d['batch'],b);d.update(status='Reserved');save(c,'reservations',d)
 elif k in ('cancel_reservation','deliver'):
  r=get(c,d['id'],'reservations')
  if r['status']!='Reserved':raise ValueError('Reservation already processed')
  b=get(c,r['batch'],'batches')
  if k=='deliver' and b['status']!='Released for sale':raise ValueError('Batch is on hold')
  b['reserved']-=float(r['quantity']);r['status']='Delivered' if k=='deliver' else 'Cancelled'
  if k=='deliver':b['delivered']=float(b.get('delivered',0))+float(r['quantity'])
  update(c,r['batch'],b);update(c,d['id'],r)
  if k=='deliver':save(c,'outbox',dict(type='inventory.delivered',event_id=event,reservation=d['id'],quantity=r['quantity'],manufacturing_cost=float(r['quantity'])*b['unit'],status='Pending connection'))
 elif k=='returns':
  r=get(c,d['reservation'],'reservations');q=number(d['quantity'],True)
  if r['status']!='Delivered' or q>float(r['quantity'])-float(r.get('returned',0)):raise ValueError('Return exceeds delivered quantity')
  r['returned']=float(r.get('returned',0))+q;update(c,d['reservation'],r)
  b=get(c,r['batch'],'batches');b['returned']=float(b.get('returned',0))+q;b['status']='Quarantined';update(c,r['batch'],b);save(c,k,d)
 elif k=='approve_invoice':
  invoice=get(c,d['id'],'invoices')
  if invoice['status']!='Matched':raise ValueError('Only matched invoices may be approved')
  invoice['status']='Approved';update(c,d['id'],invoice);save(c,'outbox',dict(type='payable.approved',event_id=event,invoice=d['id'],amount=invoice['amount'],division='Wholesale',status='Pending connection'))
 elif k=='supplier_returns':
  lot=c.execute('select * from lots where id=?',(d['lot_id'],)).fetchone();q=number(d['quantity'],True)
  if not lot or q>lot['quantity']:raise ValueError('Return exceeds remaining source lot')
  m=get(c,lot['material'],'materials');m['quantity']=float(m['quantity'])-q;update(c,lot['material'],m)
  c.execute('update lots set quantity=quantity-? where id=?',(q,lot['id']))
  revalue(c,lot['material'])
  c.execute('insert into movements values(?,?,?,?,?,datetime("now"))',(str(uuid.uuid4()),lot['material'],-q,lot['source_lot'],event))
  d['credit']=q*lot['cost'];save(c,k,d)
 elif k=='lot_hold':
  if d['status'] not in ('Approved','Quarantined','Rejected') or not d.get('notes'):raise ValueError('Status and inspection notes required')
  if not c.execute('select 1 from lots where id=?',(d['id'],)).fetchone():raise ValueError('Lot not found')
  c.execute('update lots set status=? where id=?',(d['status'],d['id']))
 elif k=='invoices':
  p=get(c,d['purchase'],'purchases');amount=number(d['amount'],True)
  if not d.get('number'):raise ValueError('Invoice number required')
  allocated=0
  for row in c.execute('select data from records where kind="invoices"'):
   old=json.loads(row[0])
   if old['number']==d['number'] and old.get('supplier')==p.get('supplier'):raise ValueError('Duplicate supplier invoice')
   if old.get('purchase')==d['purchase'] and old.get('status') in ('Matched','Approved'):allocated+=float(old['amount'])
  expected=float(p.get('received',0))*(float(p['cost'])+float(p.get('freight',0))/float(p['quantity']))
  expected-=allocated
  d.update(supplier=p.get('supplier'),status='Matched' if abs(amount-expected)<0.01 else 'Exception',expected=expected);save(c,k,d)
 elif k in ('sanitation','inspections','supplier_credits'):
  if not d.get('notes'):raise ValueError('Notes required')
  save(c,k,d)
 else:return False
 return True
