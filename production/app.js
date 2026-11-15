// Extend the standalone workspace with manufacturing and control workflows.
document.head.insertAdjacentHTML('beforeend','<link rel="manifest" href="/manifest.json"><meta name="theme-color" content="#193d32">');
document.head.insertAdjacentHTML('beforeend','<style>aside{overflow-y:auto}nav{margin-top:28px}fieldset{border:1px solid #dfe3d9;border-radius:6px;margin:15px 0}@media print{aside,button,header{display:none}main{margin:0;padding:0}section{border:0}}@media(max-width:850px){aside{overflow:visible}nav{flex-wrap:nowrap}}</style>');
const oldRender=render,oldOpen=openForm;
const baseTable=table;table=function(data,headers,mapper){baseTable(data,headers,mapper);const section=view.lastElementChild;if(data.length>8){let input=document.createElement('input');input.placeholder='Filter these records';input.setAttribute('aria-label','Filter records');input.oninput=()=>{section.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(input.value.toLowerCase()))};section.prepend(input)}};
function safeCell(v){const allowed=/^(?:<button onclick="(?:action\('[a-z_]+','[0-9a-f-]+'\)|(?:receive|quality|holdLot|completeBatch|stageBatch|showBatchCost|editPurchase|editRecipe|editBatch|editLotCost)\('[0-9a-f-]+'\))">[A-Za-z /]+<\/button>\s*)+$/;return typeof v==='string'&&allowed.test(v)?v:esc(v)}
const definitions={
 'Supplier pricing':{kind:'prices',fields:()=>field('supplier','Supplier','text',rows('suppliers'))+field('material','Material','text',rows('materials'))+field('quantity','Purchase quantity','number')+field('unit','Purchase unit','text',units)+field('price','Price per purchase unit ($)','number')+field('freight','Freight ($)','number')+field('lead_days','Lead time (days)','number'),headers:['Supplier','Material','Landed cost / stock unit','Lead days'],row:x=>[name(x.supplier),name(x.material),money(x.landed),x.lead_days]},
 'Invoices':{kind:'invoices',fields:()=>field('purchase','Purchase order','text',rows('purchases'))+field('number','Supplier invoice number')+field('amount','Invoice amount ($)','number'),headers:['Invoice','Expected','Actual','Match status'],row:x=>[x.number,money(x.expected),money(x.amount),x.status]},
 'Reservations':{kind:'reserve',record:'reservations',fields:()=>field('batch','Released batch','text',rows('batches').filter(x=>!x.bulk && x.status==='Released for sale').map(x=>({...x,name:x.name+' / '+x.lot})))+field('reference','External order reference')+field('customer','Customer reference')+field('quantity','Package quantity','number'),headers:['Order reference','Customer','Packages','Status','Actions'],row:x=>[x.reference,x.customer,x.quantity,x.status,x.status==='Reserved'?`<button onclick="action('deliver','${x.id}')">Deliver</button> <button onclick="action('cancel_reservation','${x.id}')">Cancel</button>`:'']},
 'Returns':{kind:'returns',fields:()=>field('reservation','Delivered reference','text',rows('reservations').filter(x=>x.status==='Delivered').map(x=>({...x,name:x.reference})))+field('quantity','Returned packages','number')+field('notes','Reason / condition'),headers:['Reservation','Quantity','Notes'],row:x=>[x.reservation,x.quantity,x.notes]},
 'Stock adjustments':{
  kind:'adjust', record:'stock_adjustments',
  fields:()=>field('material','Material','text',rows('materials'))+
    '<label>Quantity change (negative to subtract)<input name="quantity" type="number" step="any" required></label>'+
    field('lot','Lot')+field('reason','Reason'),
  headers:['Recorded (UTC)','Material','Quantity change','Lot','Reason'],
  row:x=>[x.created,name(x.material),x.quantity,x.lot,x.reason]
 },
 'Sanitation':{kind:'sanitation',fields:()=>field('name','Equipment / area')+field('date','Completed on','date')+field('notes','Cleaning procedure and findings'),headers:['Equipment','Date','Findings'],row:x=>[x.name,x.date,x.notes]}
};
definitions['Supplier returns']={kind:'supplier_returns',fields:()=>field('lot_id','Source lot','text',(state.lots||[]).filter(x=>x.quantity>0).map(x=>({id:x.id,name:name(x.material)+' / '+x.source_lot})))+field('quantity','Quantity in stock unit','number')+field('notes','Return / credit reference'),headers:['Lot','Quantity','Reference','Credit amount'],row:x=>[state.lots.find(lot=>lot.id===x.lot_id)?.source_lot || x.lot_id,x.quantity,x.notes,money(x.credit)]};
definitions['Waste']={kind:'writeoff',record:'writeoffs',fields:()=>field('batch','Finished lot','text',rows('batches'))+field('quantity','Packages to write off','number')+field('notes','Waste, rejection or rework reason'),headers:['Batch','Packages','Cost','Reason'],row:x=>[name(x.batch),x.quantity,money(x.cost),x.notes]};
definitions['Invoices'].headers.push('Approval');const invoiceRow=definitions['Invoices'].row;definitions['Invoices'].row=x=>[...invoiceRow(x),x.status==='Matched'?`<button onclick="action('approve_invoice','${x.id}')">Approve payable</button>`:''];
const units=['lb','oz','g','kg','each','bag','case'].map(x=>({id:x,name:x}));
let signedInRole = '';
let backgroundConnectionActive=false,backgroundRefreshRunning=false;
const costPages = ['Reports', 'Supplier pricing', 'Invoices', 'Integration queue', 'Employees'];
const scheduleQuantity = new Intl.NumberFormat(undefined, {maximumFractionDigits: 6});
const canManage = () => signedInRole === 'manager';
const canPurchase = () => canManage() || signedInRole === 'purchasing';
const canProduce = () => canManage() || signedInRole === 'operator';

async function showScheduleRequirements(entry) {
  view.innerHTML = '<h1>' + esc(entry.product) + '</h1>' +
    '<button type="button" onclick="renderSchedule()">Back to schedule</button>' +
    '<p>' + esc(entry.date) + ' · ' + esc(entry.batch_count) + ' batches</p>' +
    (entry.notes ? '<p>' + esc(entry.notes) + '</p>' : '') +
    '<p id="requirements-status" role="status">Calculating materials…</p>';
  const status = document.getElementById('requirements-status');
  try {
    const response = await fetch('/api/schedule/' + encodeURIComponent(entry.id));
    const result = await response.json();
    if (!status.isConnected) return;
    if (!response.ok) throw new Error(result.error);
    if (!result.has_recipe) {
      status.textContent = 'A manager must select an approved recipe for this run to calculate material requirements.';
      return;
    }
    status.textContent = 'Expected finished yield: ' + scheduleQuantity.format(result.expected_yield) + ' lb.';
    const showCost = result.estimated_material_cost !== undefined;
    const headers = ['Material', 'Stock unit', 'Required', 'Usable stock', 'Shortage'];
    if (showCost) headers.push('Estimated cost');
    table(result.lines, headers, line => [
      line.name, line.unit, ...[line.required, line.available, line.shortage].map(value => scheduleQuantity.format(value)),
      ...(showCost ? [money(line.estimated_cost)] : [])
    ]);
    if (showCost) {
      view.insertAdjacentHTML('beforeend', '<p>Estimated materials: ' + money(result.estimated_material_cost) +
        ' · Planned labor and overhead: ' + money(result.planned_extra_cost) +
        '</p><p><strong>Estimated total run cost: ' + money(result.estimated_total_cost) +
        '</strong></p><p>Material estimates use current inventory unit costs. Finished inventory uses actual batch costs.</p>');
    }
    if (entry.status === 'Planned' && ['manager', 'operator'].includes(signedInRole)) {
      const start = document.createElement('button');
      start.className = 'primary';
      start.type = 'button';
      start.textContent = 'Start scheduled run';
      start.onclick = () => startBatch(entry);
      view.querySelector('#requirements-status').after(start);
    }
  } catch (error) {
    if (status.isConnected) status.textContent = error.message;
  }
}

function renderSchedule() {
  const canEdit = signedInRole === 'manager';
  const entries = [...rows('production_schedule')].sort((a, b) =>
    (a.date + a.start_time).localeCompare(b.date + b.start_time));
  view.innerHTML = '<h1>Production Schedule</h1><div class="bar"><button type="button" onclick="load()">Refresh schedule</button>' +
    (canEdit ? '<button class="primary" onclick="editSchedule()">+ Schedule a run</button>' : '') + '</div>';
  if (!entries.length) {
    view.insertAdjacentHTML('beforeend', '<section><p>No production runs scheduled.</p></section>');
    return;
  }
  const headers = ['Date', 'Start time', 'Product or task', 'Recipe', 'Batches', 'Status', 'Instructions'];
  if (canEdit) headers.push('Actions');
  table(entries, headers, entry => {
    const cells = [entry.date, entry.start_time || '—', entry.product, entry.recipe_label,
      entry.batch_count, entry.status, entry.notes];
    return canEdit ? [...cells, ''] : cells;
  });
  view.querySelectorAll('tbody tr').forEach((row, index) => {
    const details = document.createElement('button');
    details.type = 'button';
    details.onclick = () => showScheduleRequirements(entries[index]);
    row.cells[2].replaceChildren(details);
    details.textContent = entries[index].product;
    details.setAttribute('aria-label', 'View requirements for ' + entries[index].product);
    if (canEdit && entries[index].status === 'Planned') {
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.textContent = 'Edit';
      edit.onclick = () => editSchedule(entries[index]);
      row.lastElementChild.append(edit);
    }
  });
}

function printInventoryControls() {
  return '<button class="primary" type="button" onclick="window.print()">Print inventory</button>' +
    '<p class="inventory-print-date">Backwoods Production · ' +
    esc(new Date().toLocaleString()) + '</p>';
}

document.head.insertAdjacentHTML('beforeend', `<style>
  .inventory-print-date { display: none; }
  @media print {
    @page inventory { size: landscape; margin: 12mm; }
    main:has(.inventory-print-date) { page: inventory; }
    .inventory-print-date { display: block; }
    section { padding: 0; overflow: visible; }
    section > input, .inventory-actions, dialog { display: none; }
    th, td { padding: 6px; font-size: 10pt; }
    thead { display: table-header-group; }
    tr { break-inside: avoid; }
  }
</style>`);

function renderFinishedInventory() {
  const showCost = signedInRole === 'manager';
  const onHand = batch => Math.max(0, +batch.packages - (batch.delivered || 0) -
    (batch.written_off || 0) + (batch.returned || 0) - (batch.converted_units || 0) - (batch.vendor_transferred || 0));
  const batches = rows('batches').filter(batch => batch.status !== 'In Production' && onHand(batch) > 0);
  const today = new Intl.DateTimeFormat('sv-SE').format(new Date());
  const unreserved = batch => onHand(batch) - (batch.reserved || 0);
  const canPackage = batch => unreserved(batch) > 1e-10 &&
    ['Approved', 'Released for sale'].includes(batch.status) &&
    (!batch.best_by || batch.best_by >= today);
  view.innerHTML = '<h1>Finished inventory</h1>';
  if (showCost) {
    view.insertAdjacentHTML('beforeend', printInventoryControls());
    const value = batches.reduce((sum, batch) => sum + onHand(batch) * (batch.unit ?? 0), 0);
    view.insertAdjacentHTML('beforeend', '<p><strong>Total on-hand cost: ' + money(value) + '</strong></p>');
    const eligible = batches.filter(canPackage);
    if (eligible.length) {
      const options = eligible.map(batch => ({
        id: batch.id, name: batch.lot + ' · ' + batch.name + ' · ' +
          scheduleQuantity.format(unreserved(batch) * batch.output / batch.packages) + ' lb available'
      }));
      view.insertAdjacentHTML('beforeend', '<section class="inventory-actions" aria-label="Package finished stock">' +
        field('source_lot', 'Lot to package', 'text', options) +
        '<button class="primary" type="button" id="package-stock">Package stock</button></section>');
    } else {
      const guidance = !batches.length
        ? 'Complete a batch in Production to create finished stock, then approve its lot in Quality & Release.'
        : 'Choose an approved or released lot with unreserved stock and a valid best-by date. Lots awaiting inspection can be approved in Quality & Release.';
      view.insertAdjacentHTML('beforeend', '<section class="inventory-actions" aria-label="Package finished stock">' +
        '<button class="primary" type="button" disabled>Package stock</button><p>' + guidance +
        '</p><button type="button" onclick="go(\'' + (batches.length ? 'Quality & release' : 'Production') +
        '\')">' + (batches.length ? 'Open Quality & Release' : 'Open Production') + '</button></section>');
    }
  }
  const headers = ['SKU / lot', 'Product', 'Packages on hand', 'Pounds on hand', 'Reserved', 'Available to sell', 'Quality'];
  if (showCost) headers.push('Cost / package', 'Cost / lb', 'On-hand cost', 'Action');
  table(batches, headers, batch => [
    (batch.sku || '') + ' / ' + batch.lot + (batch.source_lot ? ' (from ' + batch.source_lot + ')' : ''),
    batch.name, batch.bulk ? 'Bulk' : onHand(batch),
    scheduleQuantity.format(batch.output * onHand(batch) / batch.packages), batch.reserved || 0,
    !batch.bulk && batch.status === 'Released for sale' && (!batch.best_by || batch.best_by >= today)
      ? Math.max(0, onHand(batch) - (batch.reserved || 0)) : 0,
    batch.status, ...(showCost ? [batch.bulk ? '—' : money(batch.unit), money(batch.per_lb), money(onHand(batch) * batch.unit), ''] : [])
  ]);
  if (showCost) {
    const packageButton = view.querySelector('#package-stock');
    if (packageButton) {
      packageButton.onclick = () => {
        const batch = batches.find(item => item.id === view.querySelector('[name="source_lot"]').value);
        openPackaging(batch, unreserved(batch) * batch.output / batch.packages);
      };
    }
    view.querySelector('thead th:last-child')?.classList.add('inventory-actions');
    view.querySelectorAll('tbody tr').forEach((row, index) => {
      const batch = batches[index];
      const available = onHand(batch) - (batch.reserved || 0);
      const cell = row.lastElementChild;
      cell.classList.add('inventory-actions');
      const costButton = document.createElement('button');
      costButton.type = 'button';
      costButton.textContent = 'Cost breakdown';
      costButton.onclick = () => showBatchCost(batch.id);
      cell.append(costButton);
      if (!canPackage(batch)) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = 'Package stock';
      button.onclick = () => openPackaging(batch, available * batch.output / batch.packages);
      cell.append(button);
    });
  }
}

function openPackaging(batch, availableWeight) {
  operation = 'package_inventory';
  pending = crypto.randomUUID();
  formtitle.textContent = 'Package finished stock';
  const packagingOptions = [{id: '', name: 'No packaging item selected'}, ...rows('materials')
    .filter(material => ['each', 'bag'].includes(material.unit))];
  fields.innerHTML = '<p>Source lot ' + esc(batch.lot) + ' · ' +
    scheduleQuantity.format(availableWeight) + ' lb unreserved</p>' +
    '<input type="hidden" name="batch">' + field('sku', 'Packaged product SKU') +
    field('lot', 'New packaged lot') +
    '<label>Package count<input name="packages" type="number" min="1" step="1" required></label>' +
    field('weight_oz', 'Net weight per bag (oz)', 'number') +
    '<p id="packaging-weight-check" aria-live="polite"></p>' +
    field('packaging_material', 'Packaging from inventory (one per finished package)', 'text', packagingOptions) +
    '<label>Packaging labor for this run ($)<input name="labor" type="number" min="0" step="0.01"></label>' +
    '<label>Other packaging costs ($)<input name="packaging_cost" type="number" min="0" step="0.01"></label>';
  fields.querySelector('[name="batch"]').value = batch.id;
  fields.querySelector('[name="packaging_material"]').required = false;
  const count = fields.querySelector('[name="packages"]');
  const weight = fields.querySelector('[name="weight_oz"]');
  const weightCheck = fields.querySelector('#packaging-weight-check');
  function checkWeight() {
    count.setCustomValidity('');
    const perPackage = weight.valueAsNumber / 16;
    if (!(perPackage > 0)) {
      weightCheck.textContent = 'Enter the net weight in ounces, for example 8.';
      return;
    }
    const packageCount = count.valueAsNumber;
    const maxCount = Math.floor((availableWeight + 1e-10) / perPackage);
    const needed = packageCount * perPackage;
    weightCheck.textContent = 'Up to ' + scheduleQuantity.format(maxCount) +
      ' packages by weight. ' + (packageCount > 0
        ? scheduleQuantity.format(needed) + ' lb needed of ' +
          scheduleQuantity.format(availableWeight) + ' lb available.' : '');
    if (packageCount > maxCount) {
      count.setCustomValidity('Reduce the package count or weight per package.');
    }
  }
  count.addEventListener('input', checkWeight);
  weight.addEventListener('input', checkWeight);
  checkWeight();
  error.textContent = '';
  modal.showModal();
}

async function showBatchCost(id) {
  const batch = rows('batches').find(record => record.id === id);
  if (!batch || signedInRole !== 'manager') return;
  const dialog = document.createElement('dialog');
  dialog.innerHTML = '<h2>Cost breakdown</h2><p>' + esc(batch.name) + ' · ' + esc(batch.lot) +
    '</p><div aria-live="polite">Loading costs…</div><form method="dialog"><button>Close</button></form>';
  dialog.addEventListener('close', () => dialog.remove(), {once: true});
  document.body.append(dialog);
  dialog.showModal();
  const details = dialog.querySelector('div');
  try {
    const response = await fetch('/api/batch-cost/' + encodeURIComponent(id));
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    details.innerHTML = '<table><thead><tr><th>Cost component</th><th>Quantity</th><th>Cost</th></tr></thead><tbody>' +
      result.lines.map(line => '<tr><td>' + esc(line.name) + '</td><td>' +
        (line.quantity === undefined ? '—' : esc(scheduleQuantity.format(line.quantity) + ' ' + line.unit)) +
        '</td><td>' + money(line.cost) + '</td></tr>').join('') +
      '</tbody></table><p><strong>Total batch cost: ' + money(result.total) + '</strong></p>' +
      '<p>Cost per pound: ' + money(result.per_lb) +
      (result.per_package === null ? '' : ' · Cost per package: ' + money(result.per_package)) + '</p>';
  } catch (error) {
    details.textContent = error.message;
  }
}

function finishedPackageFields(label) {
  return '<label>Finished inventory type<select name="bulk" onchange="this.form.elements.packages.disabled=this.value===\'true\'">' +
    '<option value="false">Packaged</option><option value="true">Bulk (track by weight)</option></select></label>' +
    field('packages', label, 'number');
}

function editSchedule(entry = {}) {
  operation = 'save_schedule';
  pending = crypto.randomUUID();
  formtitle.textContent = entry.id ? 'Edit production run' : 'Schedule a production run';
  const recipes = [{id: '', name: 'No recipe selected'}, ...rows('recipes')
    .filter(recipe => recipe.status === 'Approved')
    .map(recipe => ({id: recipe.id, name: recipe.name + ' / version ' + recipe.version}))];
  const statuses = ['Planned', 'Completed', 'Cancelled'].map(status => ({id: status, name: status}));
  fields.innerHTML = '<input name="id" type="hidden">' + field('date', 'Production date', 'date') +
    '<label>Start time (optional)<input name="start_time" type="time"></label>' +
    '<label>Product or task<input name="product" placeholder="Defaults to the selected recipe name"></label>' +
    '<label>Planned batches<input name="batch_count" type="number" min="1" step="1" required></label>' +
    field('recipe', 'Approved recipe', 'text', recipes) +
    '<label>Planned labor and overhead for this run ($)<input name="planned_extra_cost" type="number" min="0" step="0.01"></label>' +
    field('status', 'Status', 'text', statuses) +
    '<label>Instructions for production staff<textarea name="notes" rows="3"></textarea></label>';
  const recipeInput = fields.querySelector('[name="recipe"]');
  const statusInput = fields.querySelector('[name="status"]');
  const defaults = {date: new Intl.DateTimeFormat('sv-SE').format(new Date()), batch_count: 1,
    status: 'Planned', recipe: recipes.length === 2 ? recipes[1].id : '', ...entry};
  for (const input of fields.querySelectorAll('[name]')) {
    input.value = defaults[input.name] ?? '';
  }
  function updateRecipeRequirement() {
    recipeInput.required = statusInput.value === 'Planned';
    fields.querySelector('[name="product"]').required = !recipeInput.value;
  }
  recipeInput.addEventListener('change', updateRecipeRequirement);
  statusInput.addEventListener('change', updateRecipeRequirement);
  updateRecipeRequirement();
  error.textContent = '';
  modal.showModal();
}

render=function(){
 if(!pages.includes(page))page='Overview';
 nav.innerHTML=pages.map(label=>`<button class="${page===label?'active':''}" onclick="go('${label}')">${label}</button>`).join('');
 if(page==='Employees'){
  view.innerHTML='<h1>Employees</h1><p class="muted">Manager, purchasing and operator access.</p><button class="primary" onclick="employee()">+ Add employee</button><div id="employees" role="status">Loading employees…</div>';
  const target=document.getElementById('employees');
  fetch('/api/users').then(r=>r.json()).then(data=>{
    if(target.isConnected)target.textContent=Array.isArray(data)?data.map(x=>x.name+' · '+x.username+' · '+x.role).join(' | '):data.error;
  }).catch(()=>{if(target.isConnected)target.textContent='Could not load employees. Reopen this tab to retry.'});
  return;
 }
 if(page==='Material lots'){view.innerHTML='<h1>Material lots</h1><p class="muted">Source lots and remaining stock. Expired lots cannot be manufactured.</p>';table(state.lots||[],['Source lot','Material','Quantity',...(signedInRole==='manager'?['Unit cost']:[]),'Expiry','Status','Action'],x=>[x.source_lot,name(x.material),x.quantity,...(signedInRole==='manager'?[money(x.cost)]:[]),x.expires,x.status,signedInRole==='manager'?`<button onclick="holdLot('${x.id}')">Inspect / hold</button> <button onclick="editLotCost('${x.id}')">Correct cost</button>`:'']);return}
 if(page==='Connections' && state.connections?.connected){
  const connection=state.connections;
  view.innerHTML='<h1>Connections</h1><section><h2>Backwoods app connections</h2><p>Wholesale Vendor Ordering · '+esc(connection.vendor)+'</p><p>Central Accounting · '+esc(connection.accounting)+'</p><p>Backwoods Employees · Access managed by Employee/Employer</p><p class="muted">'+esc(connection.message)+'</p></section>';return;
 }
 if(page==='Integration queue'){view.innerHTML='<h1>Integration queue</h1><p class="muted">'+(state.connections?.connected?'Production records are sent in the background. Vendor tracks transferred inventory; check Accounting for completed imports.':'Pending events for future Backwoods connections. No external records have been sent.')+'</p>';table(rows('outbox'),['Event type','Event ID','Status'],x=>[x.type,x.event_id,x.status]);return}
 if(page==='Finished inventory'){renderFinishedInventory();return}
 if(page==='Production Schedule'){renderSchedule();return}
 if(definitions[page]){
  const cfg=definitions[page];
  const canAdd=canManage() || (page==='Sanitation' && canProduce());
  view.innerHTML=`<h1>${esc(page)}</h1>`+(canAdd?`<button class="primary" onclick="openAdvanced('${page}')">+ Add record</button>`:'');
  const visible=cfg.headers.map(label=>canManage() || !['Cost','Credit amount','Actions'].includes(label));
  table(rows(cfg.record||cfg.kind),cfg.headers.filter((_,i)=>visible[i]),row=>cfg.row(row).filter((_,i)=>visible[i]));
  return;
 }
 if(page==='Audit history'||page==='Traceability'){view.innerHTML=`<h1>${esc(page)}</h1>`;if(page==='Audit history')table(state.events,['Event','Operation','Time'],x=>[x.id,x.kind,x.created]);else{view.innerHTML+='<p class="muted">Source lots and suppliers consumed into finished batches, with forward customer references.</p>';table(rows('batches'),['Finished lot','Product','Recipe version','Source lots','Customer references','Status'],x=>[x.lot,x.name,x.recipe_snapshot?.version,[...(x.source_lot?[x.source_lot]:[]),...(x.inputs||[]).flatMap(i=>(i.lots||[]).map(l=>l.source_lot+' / '+name(l.supplier)+' / '+l.quantity))].join('; '),rows('reservations').filter(r=>r.batch===x.id).map(r=>r.customer+' / '+r.reference+' / '+r.status).join('; '),x.status])}return}
 oldRender();
 if((['Suppliers','Materials'].includes(page) && !canPurchase()) ||
    (page==='Overview' && !canProduce())) view.querySelector('.bar button')?.remove();
 if(page==='Quality & release' && !canManage()) {
  for(const cell of view.querySelectorAll('thead th:last-child, tbody td:last-child'))cell.remove();
 } else if(page==='Quality & release') {
  const batches=rows('batches');
  view.querySelectorAll('tbody tr').forEach((row,index)=>{
    if(!qualityDecisions(batches[index]).length) row.lastElementChild.replaceChildren();
  });
 }
 if(page==='Materials' && signedInRole==='manager') view.querySelector('h1').insertAdjacentHTML('afterend', printInventoryControls());
 if(page==='Overview'){let alerts=rows('materials').filter(x=>+x.quantity<=+x.reorder).map(x=>'Reorder: '+x.name+' ('+x.quantity+' '+(x.unit||'lb')+')');alerts.push(...rows('prices').filter(x=>x.increase>0).map(x=>'Supplier price increased: '+name(x.material)+' / '+name(x.supplier)+' by '+money(x.increase)+' per stock unit'));if(alerts.length)view.insertAdjacentHTML('beforeend','<section><h2>Needs attention</h2><p>'+alerts.map(esc).join('<br>')+'</p></section>')}
 if(page==='Reports'){view.insertAdjacentHTML('beforeend','<section><h2>Margin estimate</h2><label>Selling price per package ($)<input id="sellprice" type="number" min="0" step="0.01" oninput="marginReport(this.value)"></label><div id="marginresult"></div><p class="muted">Estimates use manufacturing costs and exclude sales expenses. Customer pricing remains with wholesale ordering.</p></section>');table(rows('batches'),['Lot','Standard materials','Material variance','Expected yield','Yield variance'],x=>[x.lot,money(x.standard_material_cost),money(x.material_variance),x.expected_output,x.yield_variance])}
 if(page==='Purchasing'){
  view.innerHTML='<h1>Purchasing</h1>'+(canPurchase()?'<button class="primary" onclick="openForm(\'purchases\')">+ Create purchase order</button>':'');
  table(rows('purchases'),['Purchase order','Material','Ordered','Received','Status','Action'],purchase=>{
    let actions='';
    if(purchase.status==='Draft' && canManage()) {
      actions=`<button onclick="editPurchase('${purchase.id}')">Edit draft</button> <button onclick="action('approve_purchase','${purchase.id}')">Approve order</button>`;
    } else if(purchase.status==='Approved' && canPurchase() && Number(purchase.received || 0)<Number(purchase.quantity)) {
      actions=`<button onclick="receive('${purchase.id}')">Receive</button>`;
    }
    return [purchase.name,name(purchase.material),purchase.quantity,purchase.received||0,purchase.status,actions];
  });
 }
 if(page==='Recipes'){view.innerHTML='<h1>Recipe versions</h1><p class="muted">Each approved version preserves its ingredients and packaging. Create a new version to revise a recipe.</p>'+(canManage()?'<button class="primary" onclick="bom()">+ Create recipe version</button>':'');table(rows('recipes'),['Recipe','Version','State','Action'],x=>[x.name,x.version,x.status||'Legacy',x.status==='Draft'&&canManage()?`<button onclick="editRecipe('${x.id}')">Edit draft</button> <button onclick="action('approve_recipe','${x.id}')">Approve version</button>`:''])}
 if(page==='Production'){
  const showCost = signedInRole === 'manager';
  view.innerHTML='<h1>Production batches</h1>'+(canProduce()?'<button class="primary" onclick="startBatch()">+ Start production batch</button> <button onclick="manufacture()">Record completed batch</button>':'');
  table(rows('batches'), ['Lot','Product','Usable lb',...(showCost ? ['Total cost'] : []),'Status','Action'], batch => {
    let actions = '';
    if (batch.status === 'In Production' && canProduce()) {
      actions = `<button onclick="completeBatch('${batch.id}')">Complete batch</button> <button onclick="stageBatch('${batch.id}')">Record stage</button>`;
    } else if (showCost) {
      actions = `<button onclick="showBatchCost('${batch.id}')">Cost breakdown</button>`;
      if (batch.status === 'Awaiting inspection' && !batch.source_batch) {
        actions += ` <button onclick="editBatch('${batch.id}')">Edit batch</button>`;
      }
    }
    return [batch.lot, batch.name, batch.output, ...(showCost ? [money(batch.total)] : []), batch.status, actions];
  });
 }
};
function fillFields(record, container = fields) {
  for (const input of container.querySelectorAll('[name]')) {
    if (record[input.name] !== undefined) input.value = record[input.name];
  }
}

function editPurchase(id) {
  openForm('purchases');
  operation = 'edit_purchase';
  formtitle.textContent = 'Edit draft purchase order';
  fields.insertAdjacentHTML('afterbegin', '<input type="hidden" name="id">');
  fillFields(rows('purchases').find(record => record.id === id));
}

function editRecipe(id) {
  const recipe = rows('recipes').find(record => record.id === id);
  bom();
  formtitle.textContent = 'Edit draft recipe';
  fields.insertAdjacentHTML('afterbegin', '<input type="hidden" name="id">');
  fillFields(recipe);
  const lineContainer = document.getElementById('bomlines');
  lineContainer.replaceChildren();
  for (const line of recipe.lines) {
    addLine();
    fillFields(line, lineContainer.lastElementChild);
  }
}

function editBatch(id) {
  const batch = rows('batches').find(record => record.id === id);
  completeBatch(id);
  operation = 'edit_batch';
  formtitle.textContent = 'Edit batch before inspection';
  fillFields({...batch, bulk: String(Boolean(batch.bulk)), labor: batch.labor || 0,
    energy: batch.energy || 0, overhead: batch.overhead || 0, other: batch.other || 0});
  fields.querySelector('[name="packages"]').disabled = Boolean(batch.bulk);
}

function editLotCost(id) {
  const lot = state.lots.find(record => record.id === id);
  operation = 'correct_lot_cost';
  pending = crypto.randomUUID();
  formtitle.textContent = 'Correct material lot cost';
  fields.innerHTML = '<p>' + esc(name(lot.material)) + ' · ' + esc(lot.source_lot) +
    '</p><p>This recalculates the cost of unfinished batches that used this lot.</p>' +
    '<input type="hidden" name="id">' + field('cost', 'Correct cost per stock unit ($)', 'number') +
    field('reason', 'Reason for correction');
  fillFields(lot);
  error.textContent = '';
  modal.showModal();
}
function marginReport(value){let price=Number(value);document.getElementById('marginresult').textContent=rows('batches').filter(x=>x.packages>0).map(x=>x.name+' / '+x.lot+': '+money(price-x.unit)+' profit per package, '+(price>0?((price-x.unit)/price*100).toFixed(1):'0')+'% gross margin').join(' | ')}
function startBatch(run) {
  operation = 'start_batch';
  pending = crypto.randomUUID();
  formtitle.textContent = 'Start production';
  const recipeFields = run
    ? '<input type="hidden" name="schedule_id" value="' + esc(run.id) + '"><p>' +
      esc(run.recipe_label) + ' · ' + esc(run.batch_count) + ' recipe batches. Starting deducts the required materials.</p>'
    : field('recipe','Approved recipe','text',rows('recipes').filter(x=>x.status==='Approved')) +
      field('scale','Batch multiplier','number');
  fields.innerHTML = recipeFields + field('lot','Finished lot') + field('sku','SKU') +
    field('equipment','Equipment') + field('date','Start date','date');
  fields.querySelector('[name="date"]').value = new Intl.DateTimeFormat('sv-SE').format(new Date());
  error.textContent = '';
  modal.showModal();
}
function completeBatch(id){operation='complete_batch';pending=crypto.randomUUID();formtitle.textContent='Complete production and packaging';fields.innerHTML=`<input type="hidden" name="id" value="${id}">`+field('output','Actual usable weight (lb)','number')+finishedPackageFields('Finished packages')+field('best_by','Best by','date')+field('profile','Roast / seasoning observations')+['labor','energy','overhead','other'].map(k=>field(k,k+' cost ($)','number')).join('');error.textContent='';modal.showModal()}
function stageBatch(id){operation='batch_stage';pending=crypto.randomUUID();formtitle.textContent='Production stage';fields.innerHTML=`<input type="hidden" name="id" value="${id}">`+field('stage','Stage','text',['Roasting','Seasoning','Tumbling','Packaging'].map(x=>({id:x,name:x})))+field('notes','Temperatures, timing, checks and observations');error.textContent='';modal.showModal()}
function employee(){operation='users';pending=crypto.randomUUID();formtitle.textContent='Add employee';fields.innerHTML=field('name','Name')+field('username','Username')+field('password','Initial password (12+ characters)','password')+field('role','Role','text',['manager','purchasing','operator'].map(x=>({id:x,name:x})));error.textContent='';modal.showModal()}
function holdLot(id){operation='lot_hold';pending=crypto.randomUUID();formtitle.textContent='Incoming quality inspection';fields.innerHTML=`<input name="id" type="hidden" value="${id}">`+field('status','Decision','text',['Approved','Quarantined','Rejected'].map(x=>({id:x,name:x})))+field('notes','Inspection / allergen / condition notes');error.textContent='';modal.showModal()}
const draftButton=document.createElement('button');draftButton.type='button';draftButton.textContent='Save draft on this device';draftButton.onclick=()=>{if(operation==='users')return;const d={operation,event_id:pending,fields:fields.innerHTML,values:[...fields.querySelectorAll('input,select,textarea')].map(x=>x.value)};localStorage.setItem('bw-draft',JSON.stringify(d));error.textContent='Draft saved on this device. Review and submit when connected.'};form.append(draftButton);
const restoreButton=document.createElement('button');restoreButton.textContent='Restore local draft';restoreButton.onclick=()=>{let d=JSON.parse(localStorage.getItem('bw-draft')||'null');if(!d)return alert('No saved draft.');operation=d.operation;pending=d.event_id;fields.innerHTML=d.fields;[...fields.querySelectorAll('input,select,textarea')].forEach((x,i)=>x.value=d.values[i]);formtitle.textContent='Review saved draft';error.textContent='';modal.showModal()};document.querySelector('header').append(restoreButton);
openForm=function(kind,extra=''){if(kind==='recipes')return bom();if(kind==='batches')return manufacture();oldOpen(kind,extra);if(kind==='materials')fields.innerHTML=field('name','Material name')+field('quantity','Opening quantity in stock unit','number')+field('cost','Cost per stock unit ($)','number')+field('reorder','Reorder point in stock unit','number')+field('unit','Stock unit','text',units)+field('lot','Opening lot reference')+field('location','Storage location');if(kind==='suppliers')fields.insertAdjacentHTML('beforeend',['address','account','minimum_order','freight_terms','notes'].map(k=>field(k,k.replaceAll('_',' '))).join(''));if(kind==='receive')fields.insertAdjacentHTML('beforeend',field('expires','Best by','date')+field('location','Storage location'));if(kind==='purchases'){fields.innerHTML=field('name','Purchase order number')+field('supplier','Supplier','text',rows('suppliers'))+field('material','Material','text',rows('materials'))+field('quantity','Quantity in material stock unit','number')+field('cost','Price per material stock unit ($)','number')+field('freight','Total freight ($)','number')}};
function qualityDecisions(batch) {
  const decisions = {
    'Awaiting inspection':['Approved','Quarantined','Rejected'],
    Approved:['Released for sale','Quarantined'],
    Quarantined:['Approved','Rejected'],
    'Released for sale':['Quarantined']
  }[batch.status] || [];
  return batch.bulk ? decisions.filter(decision => decision !== 'Released for sale') : decisions;
}
quality=function(id){
  const batch=rows('batches').find(item=>item.id===id);
  const decisions=qualityDecisions(batch);
  if(!decisions.length)return;
  openForm('quality',`<input type="hidden" name="id" value="${id}">`+
    field('status','Decision','text',decisions.map(decision=>({id:decision,name:decision})))+
    field('notes','Inspection findings and release notes'));
};
function openAdvanced(p){let cfg=definitions[p];operation=cfg.kind;pending=crypto.randomUUID();formtitle.textContent=p;fields.innerHTML=cfg.fields();error.textContent='';modal.showModal()}
function bom(){operation='recipe_versions';pending=crypto.randomUUID();formtitle.textContent='Recipe bill of materials';fields.innerHTML=field('name','Product name')+field('version','Version')+field('batch_size','Standard batch size (lb)','number')+field('expected_yield','Expected finished weight (lb)','number')+field('instructions','Production and allergen instructions')+'<div id="bomlines"></div><button type="button" onclick="addLine()">+ Add ingredient / packaging</button>';addLine();error.textContent='';modal.showModal()}
function addLine(){document.getElementById('bomlines').insertAdjacentHTML('beforeend','<fieldset class="bomline">'+field('material','Material','text',rows('materials'))+field('quantity','Quantity per batch','number')+field('unit','Unit','text',units)+'<button type="button" onclick="this.parentElement.remove()">Remove</button></fieldset>')}
function manufacture(){operation='manufacture';pending=crypto.randomUUID();formtitle.textContent='Manufacture batch';fields.innerHTML=field('recipe','Approved recipe','text',rows('recipes').filter(x=>x.status==='Approved'))+field('lot','Finished lot')+field('sku','Finished SKU')+field('equipment','Roaster / equipment')+field('profile','Roast profile, temperature, duration and seasoning observations')+field('date','Production date','date')+field('best_by','Best by','date')+field('scale','Batch multiplier','number')+field('output','Actual usable output (lb)','number')+finishedPackageFields('Saleable packages')+['labor','energy','overhead','other'].map(k=>field(k,k+' cost ($)','number')).join('');error.textContent='';modal.showModal()}
async function action(kind,id){try{await post(kind,{id,event_id:crypto.randomUUID()});await load()}catch(e){alert(e.message)}}
async function post(kind,data){let r=await fetch('/api/'+kind,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});let j=await r.json();if(!r.ok)throw Error(j.error);return j}
form.onsubmit=async e=>{e.preventDefault();let d=Object.fromEntries(new FormData(form));if('bulk' in d)d.bulk=d.bulk==='true';if(operation==='package_inventory' && 'weight_oz' in d){d.weight_per_package=Number(d.weight_oz)/16;delete d.weight_oz}if(operation==='recipe_versions'){d.lines=[...document.querySelectorAll('.bomline')].map(el=>Object.fromEntries([...el.querySelectorAll('input,select')].map(x=>[x.name,x.value])));if('confirm_imported_formula' in d)d.confirm_imported_formula=d.confirm_imported_formula==='on';delete d.material;delete d.quantity;delete d.unit}d.event_id=pending;try{await post(operation,d);modal.close();await load()}catch(e){error.textContent=e.message}};

const renderDetailPage = render;
const dailyPages = ['Overview', 'Receive supplies', 'Make a batch', 'Package & release', 'Ready to sell'];
let toolsExpanded = false;

function dailyButton(label, action, primary = false) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  if (primary) button.className = 'primary';
  button.onclick = action;
  return button;
}

function addDailyActions(actions, target = view) {
  const bar = document.createElement('div');
  bar.className = 'bar';
  for (const [label, action] of actions) bar.append(dailyButton(label, action, bar.childElementCount === 0));
  target.append(bar);
}

function receiveSupplies() {
  operation = 'receive_supplies';
  pending = crypto.randomUUID();
  formtitle.textContent = 'Receive supplies';
  fields.innerHTML = field('supplier', 'Supplier', 'text', rows('suppliers')) +
    field('material', 'Material', 'text', rows('materials')) +
    field('quantity', 'Quantity received', 'number') +
    field('invoice_total', 'Total for this material before freight ($)', 'number') +
    '<label>Freight for this material ($)<input type="number" name="freight" min="0" step="0.01" value="0"></label>' +
    field('name', 'Invoice or receipt reference') + field('lot', 'Supplier lot') +
    '<label>Best by (optional)<input type="date" name="expires"></label>' +
    '<label>Storage location (optional)<input name="location"></label>' +
    '<p role="status" id="receipt-cost"></p>';
  function updateReceiptCost() {
    const data = new FormData(form);
    const material = rows('materials').find(item => item.id === data.get('material'));
    const quantity = Number(data.get('quantity'));
    const total = Number(data.get('invoice_total')) + Number(data.get('freight'));
    const unit = material?.unit || 'lb';
    fields.querySelector('[name="quantity"]').parentElement.firstChild.textContent =
      'Quantity received (' + unit + ')';
    fields.querySelector('#receipt-cost').textContent = quantity > 0 && data.get('invoice_total') !== ''
      ? 'Cost per ' + unit + ' with freight: $' + (total / quantity).toLocaleString('en-US', {
        minimumFractionDigits: 2, maximumFractionDigits: 6
      }) : 'Enter the quantity and total to see the unit cost.';
  }
  for (const input of fields.querySelectorAll('input, select')) input.addEventListener('input', updateReceiptCost);
  updateReceiptCost();
  error.textContent = '';
  modal.showModal();
}

function showReceiving() {
  view.innerHTML = '<h1>Receive supplies</h1>';
  const actions = [];
  if (canManage() && rows('suppliers').length && rows('materials').length) {
    actions.push(['Receive new stock', receiveSupplies]);
  } else if (canPurchase()) {
    view.insertAdjacentHTML('beforeend', '<p>Add a supplier and material before receiving stock.</p>');
    if (!rows('suppliers').length) actions.push(['Add supplier', () => go('Suppliers')]);
    if (!rows('materials').length) actions.push(['Add material', () => go('Materials')]);
  }
  if (canPurchase()) actions.push(['Open purchase orders', () => go('Purchasing')]);
  if (actions.length) addDailyActions(actions);
  const lots = [...(state.lots || [])].reverse();
  table(lots, ['Lot', 'Material', 'On hand', 'Location', 'Status'], lot => [
    lot.source_lot, name(lot.material), lot.quantity, lot.location, lot.status
  ]);
}

function showMaking() {
  renderSchedule();
  view.querySelector('h1').textContent = 'Make a batch';
  const actions = [['View batches and finish production', () => go('Production')]];
  if (canProduce()) actions.unshift(['Start from a recipe', () => startBatch()]);
  if (canManage() && !rows('recipes').some(recipe => recipe.status === 'Approved')) {
    actions.push(['Set up a recipe', () => go('Recipes')]);
  }
  const controls = document.createElement('div');
  addDailyActions(actions, controls);
  view.querySelector('h1').after(controls);
}

function showPackaging() {
  renderFinishedInventory();
  view.querySelector('h1').textContent = 'Package & release';
  if (!canManage()) return;
  const batches = rows('batches').filter(batch =>
    batch.status === 'Awaiting inspection' || (!batch.bulk && batch.status === 'Approved'));
  if (!batches.length) return;
  const queue = document.createElement('section');
  queue.className = 'inventory-actions';
  queue.innerHTML = '<h2>Inspection and release</h2>';
  for (const batch of batches) {
    const row = document.createElement('p');
    row.textContent = batch.name + ' · lot ' + batch.lot + ' ';
    const isReady = batch.status === 'Approved';
    row.append(dailyButton(isReady ? 'Release for sale' : 'Inspect this lot', () => {
      quality(batch.id);
      if (isReady) fillFields({status:'Released for sale'});
    }));
    queue.append(row);
  }
  view.querySelector('h1').after(queue);
}

function sellableCount(batch) {
  const today = new Intl.DateTimeFormat('sv-SE').format(new Date());
  if (batch.bulk || batch.status !== 'Released for sale' || (batch.best_by && batch.best_by < today)) return 0;
  return Math.max(0, Number(batch.packages) - (batch.reserved || 0) - (batch.delivered || 0) -
    (batch.written_off || 0) + (batch.returned || 0) - (batch.converted_units || 0) - (batch.vendor_transferred || 0));
}

function showSelling() {
  view.innerHTML = '<h1>Ready to sell</h1>';
  const batches = rows('batches').filter(batch => sellableCount(batch) > 0);
  const headers = ['Product', 'SKU', 'Lot', 'Available packages', 'Reserved'];
  if (canManage()) headers.push('Actions');
  table(batches, headers, batch => [batch.name, batch.sku, batch.lot, sellableCount(batch), batch.reserved || 0,
    ...(canManage() ? [''] : [])]);
  if (canManage()) view.querySelectorAll('tbody tr').forEach((row,index) => {
    const batch = batches[index];
    row.lastElementChild.append(
      dailyButton('Reserve stock', () => {openAdvanced('Reservations');fillFields({batch:batch.id});}),
      dailyButton('Cost breakdown', () => showBatchCost(batch.id)));
  });
  const heading = document.createElement('h2');
  heading.textContent = 'Reserved orders';
  view.append(heading);
  const reserved = rows('reservations').filter(order => order.status === 'Reserved');
  table(reserved, ['Order', 'Customer', 'Packages', ...(canManage() ? ['Actions'] : [])], order => [
    order.reference, order.customer, order.quantity, ...(canManage() ? [definitions.Reservations.row(order).at(-1)] : [])
  ]);
}

render = function () {
  const workflows = {'Receive supplies':showReceiving,'Make a batch':showMaking,
    'Package & release':showPackaging,'Ready to sell':showSelling};
  if (Object.hasOwn(workflows,page)) workflows[page]();
  else renderDetailPage();
  if (page === 'Overview') {
    view.innerHTML = '<h1>What are you working on?</h1>';
    const cards = document.createElement('div');
    cards.className = 'workflow-cards';
    for (const [label, description] of [
      ['Receive supplies','Record deliveries and check costs.'],
      ['Make a batch','Start a recipe or scheduled run.'],
      ['Package & release','Bag finished stock and approve it for sale.'],
      ['Ready to sell','See available stock and reserved orders.']
    ]) {
      const card = document.createElement('section');
      const descriptionNode = document.createElement('p');
      descriptionNode.textContent = description;
      card.append(dailyButton(label, () => go(label), true), descriptionNode);
      cards.append(card);
    }
    view.append(cards);
  }
  nav.replaceChildren();
  for (const label of dailyPages) {
    const button = dailyButton(label, () => go(label));
    if (page === label) button.classList.add('active');
    nav.append(button);
  }
  const tools = document.createElement('details');
  tools.open = toolsExpanded || !dailyPages.includes(page);
  tools.addEventListener('toggle', () => { toolsExpanded = tools.open; });
  const summary = document.createElement('summary');
  summary.textContent = canManage() ? 'Manager tools' : 'More tools';
  tools.append(summary);
  for (const label of pages.filter(label => label !== 'Overview')) {
    const button = dailyButton(label, () => go(label));
    if (page === label) button.classList.add('active');
    tools.append(button);
  }
  nav.append(tools);
};

document.head.insertAdjacentHTML('beforeend', '<style>.workflow-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin-top:24px}nav summary{cursor:pointer;padding:13px 14px}nav details{margin-top:12px}nav details button{padding-left:24px}.bar{gap:10px;flex-wrap:wrap}.inventory-actions button+button{margin-left:6px}@media(max-width:850px){.workflow-cards{grid-template-columns:1fr}nav details{margin-top:0}}</style>');
async function authenticate(){let me=await(await fetch('/api/me')).json();backgroundConnectionActive=!!me.central;if(me.user){signedInRole=me.user.role;if(signedInRole!=='manager'){for(const item of costPages){const i=pages.indexOf(item);if(i>=0)pages.splice(i,1)}}document.querySelector('header span:nth-of-type(2)').textContent=me.user.name+' · '+me.user.role;document.querySelector('header').insertAdjacentHTML('beforeend','<button onclick="logout()">Sign out</button>');await load();return}nav.innerHTML='';view.innerHTML='<h1>Welcome to Backwoods.</h1><section style="max-width:440px"><h2>'+(me.setup?'Create your manager account':'Sign in')+'</h2><form id="login">'+(me.setup?field('name','Your name'):'')+field('username','Username')+field('password','Password (12+ characters)','password')+'<p id="loginerror"></p><button class="primary">Continue</button></form></section>';document.getElementById('login').onsubmit=async e=>{e.preventDefault();try{await post(me.setup?'setup':'login',Object.fromEntries(new FormData(e.target)));await authenticate()}catch(e){document.getElementById('loginerror').textContent=e.message}}}
async function logout(){await post('logout',{});location.reload()}
window.addEventListener('offline',()=>{document.querySelector('header').insertAdjacentHTML('beforeend','<span>Offline · records require connection</span>')});
if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js');authenticate().catch(e=>{console.error(e);view.innerHTML='<h1>Offline workspace</h1><p>Connect to the production server to sign in and update stock. Local drafts can be restored and reviewed from the header.</p>'});

// Refresh background handoffs without changing the current screen or an open form.
async function refreshBackgroundRecords(){
 if(!backgroundConnectionActive || !signedInRole || backgroundRefreshRunning || document.hidden || modal.open)return;
 backgroundRefreshRunning=true;
 try{
  const response=await fetch('/api/state');
  if(response.status===401){backgroundConnectionActive=false;location.reload();return}
  if(!response.ok)return;
  const result=await response.json();if(!Array.isArray(result.records))return;
  state=result;
  if(!modal.open && !view.querySelector('input:focus,select:focus,textarea:focus'))render();
 }catch(error){/* Saved records remain on the server; the next refresh retries. */}
 finally{backgroundRefreshRunning=false}
}
setInterval(refreshBackgroundRecords,15000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshBackgroundRecords()});

// Categorized recipes extend the existing Recipes tool and its version workflow.
const recipeCategories=['Peanuts','Coffee','Ice Cream','Pickles'];
let recipeCategoryFilter='';
const recipeLibraryRender=render;
render=function(){recipeLibraryRender();if(page==='Recipes')showRecipeLibrary()};

function showRecipeLibrary(){
 view.innerHTML='<h1>Recipe versions</h1><p class="muted">Recipes and source notes organized by product category. Imported formulas stay as drafts until reviewed.</p>';
 const bar=document.createElement('div');bar.className='bar';
 const label=document.createElement('label');label.textContent='Product category';
 const select=document.createElement('select');select.setAttribute('aria-label','Product category');
 for(const category of ['',...new Set([...recipeCategories,...rows('recipes').map(r=>r.category||'Uncategorized')])]){
  const option=document.createElement('option');option.value=category;option.textContent=category||'All categories';select.append(option);
 }
 select.value=recipeCategoryFilter;select.onchange=()=>{recipeCategoryFilter=select.value;showRecipeLibrary()};label.append(select);bar.append(label);
 if(canManage())bar.append(dailyButton('+ Create recipe version',()=>bom(),true),dailyButton('Import recipe documents',chooseRecipeDocuments));
 view.append(bar);
 const recipes=rows('recipes').filter(r=>!recipeCategoryFilter||(r.category||'Uncategorized')===recipeCategoryFilter)
  .sort((a,b)=>(a.category||'').localeCompare(b.category||'')||a.name.localeCompare(b.name));
 table(recipes,['Recipe','Category','Range','Version','State','Actions'],r=>[r.name,r.category||'Uncategorized',r.subcategory||'',r.version,r.imported_recipe&&r.status==='Draft'?'Draft · review required':r.status||'Legacy','']);
 const recipeTable=view.lastElementChild;
 recipeTable.querySelectorAll('tbody tr').forEach((row,index)=>{
  const recipe=recipes[index];row.lastElementChild.append(dailyButton('View recipe',()=>viewRecipeSource(recipe)));
  if(canManage()&&recipe.status==='Draft'){
   row.lastElementChild.append(dailyButton('Edit draft',()=>editRecipe(recipe.id)));
   if(!recipe.imported_recipe||recipe.formula_reviewed)row.lastElementChild.append(dailyButton('Approve version',()=>action('approve_recipe',recipe.id)));
  }
 });
 const documents=rows('recipe_documents').filter(r=>!recipeCategoryFilter||r.category===recipeCategoryFilter);
 if(documents.length){
  const heading=document.createElement('h2');heading.textContent='Source documents & process notes';view.append(heading);
  table(documents,['Document','Category','Contents'],d=>[d.name,d.category,'']);
  view.lastElementChild.querySelectorAll('tbody tr').forEach((row,index)=>row.lastElementChild.append(dailyButton('Read source',()=>viewRecipeDocument(documents[index]))));
 }
}

function recipeReadDialog(title,html){
 const dialog=document.createElement('dialog');dialog.style.width='820px';
 dialog.innerHTML='<h2>'+esc(title)+'</h2>'+html;
 dialog.append(dailyButton('Close',()=>dialog.close()));dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();
}

function viewRecipeSource(recipe){
 const issues=recipe.status==='Draft'&&recipe.review_issues?.length?'<p>'+recipe.review_issues.map(esc).join('<br>')+'</p>':'';
 const variants=recipe.source_variants||[];
 const body=variants.length?variants.map((v,index)=>'<h3>Source '+(index+1)+' · '+esc(v.document)+'</h3><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(v.text)+'</pre>').join(''):'<pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(recipe.instructions||'')+'</pre>';
 recipeReadDialog(recipe.name,'<p>'+esc(recipe.category||'Uncategorized')+' · '+esc(recipe.status)+'</p>'+issues+body);
}

function viewRecipeDocument(document_){recipeReadDialog(document_.name,'<p>'+esc(document_.category)+'</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(document_.paragraphs.map(p=>p.text).join('\n\n'))+'</pre>')}

async function chooseRecipeDocuments(){
 const picker=document.createElement('input');picker.type='file';picker.accept='.odt';picker.multiple=true;
 picker.onchange=async()=>{
  try{
   const files=[...picker.files];if(!files.length)return;
   if(files.length>8||files.some(f=>f.size>2*1024*1024)||files.reduce((sum,f)=>sum+f.size,0)>6*1024*1024)throw Error('Select up to eight ODT files, no larger than 2 MB each and 6 MB together.');
   const documents=[];
   for(const file of files){
    const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
    for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
    documents.push({name:file.name,data:btoa(binary)});
   }
   const preview=await post('recipe-import/preview',{documents});
   const dialog=document.createElement('dialog');
   dialog.innerHTML='<h2>Import recipe documents</h2><p>'+esc(preview.documents)+' documents · '+esc(preview.recipes)+' recipes</p><p>'+Object.entries(preview.categories).map(([c,n])=>esc(c)+': '+esc(n)).join('<br>')+'</p><p>Original instructions and alternate versions are retained. Ingredients with missing amounts or ranges need review. Import creates draft recipes and zero-stock material references.</p><p role="status"></p>';
   const status=dialog.querySelector('[role=status]');const event_id=crypto.randomUUID();
   const confirm=dailyButton('Import drafts',async()=>{
    confirm.disabled=true;status.textContent='Importing…';
    try{const result=await post('import_recipes',{documents,event_id});dialog.close();await load();alert(result.duplicate?'This saved import already completed. Its recipes are shown in the library.':'Imported '+result.recipes+' new recipes. '+result.skipped+' already-present recipes retained.');}
    catch(e){status.textContent=e.message;confirm.disabled=false;confirm.textContent='Retry saved import';}
   },true);
   dialog.append(dailyButton('Cancel',()=>dialog.close()),confirm);dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();
  }catch(e){alert(e.message)}
 };
 picker.click();
}

const categorizedBom=bom;
bom=function(){categorizedBom();fields.insertAdjacentHTML('afterbegin',field('category','Product category','text',[{id:'',name:'Uncategorized'},...recipeCategories.map(c=>({id:c,name:c}))]));fields.querySelector('[name=category]').required=false;};
const categorizedEditRecipe=editRecipe;
editRecipe=function(id){
 categorizedEditRecipe(id);const recipe=rows('recipes').find(r=>r.id===id);
 if(recipe.imported_recipe){
  const summary=document.createElement('p');summary.textContent=recipe.review_issues.join(' ');fields.prepend(summary);
  fields.insertAdjacentHTML('beforeend','<label><input name="confirm_imported_formula" type="checkbox" required style="display:inline;width:auto"> I reviewed the original formula, base recipes, quantities and finished yield.</label>');
 }
};
