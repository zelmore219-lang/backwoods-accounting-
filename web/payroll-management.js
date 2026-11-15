// Financial preparation uses the existing Accounting API and owner permissions.
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=cents=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format((cents||0)/100);
const input=(name,label,type='text',value='',extra='')=>`<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
const amount=(name,label,value='')=>input(name,label,'number',value,'min="0" max="1000000" step="0.01" required');
const check=(name,label)=>`<label class="small"><input type="checkbox" name="${name}" required> ${label}</label>`;
const options=(rows,selected='')=>rows.map(([id,name])=>`<option value="${esc(id)}" ${id===selected?'selected':''}>${esc(name)}</option>`).join('');
const table=(headers,rows)=>`<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
const dollars=value=>{if(value===''||value===null)throw Error('Enter the actual amount, including zero where applicable.');const n=Number(value);if(!Number.isFinite(n)||n<0)throw Error('Enter a nonnegative amount.');return Math.round((n+Number.EPSILON)*100);};
const minutes=value=>{const n=Number(value||0);if(!Number.isFinite(n)||n<0)throw Error('Enter valid hours.');return String(Math.round(n*60*1000000)/1000000);};
const value=form=>Object.fromEntries(new FormData(form));
const field=(form,name)=>form.elements.namedItem(name);
export const safeCsvIdentity=value=>/^[=+\-@]/.test(String(value).trimStart())?"'"+value:String(value);
export function parseResultCsv(text){
 const rows=[];let row=[],cell='',quoted=false;
 text=text.replace(/^\uFEFF/,'');
 for(let i=0;i<text.length;i++){
  const c=text[i];
  if(quoted){if(c==='"'&&text[i+1]==='"'){cell+='"';i++;}else if(c==='"')quoted=false;else cell+=c;}
  else if(c==='"'){if(cell)throw Error('Invalid result CSV quoting.');quoted=true;}
  else if(c===','){row.push(cell);cell='';}
  else if(c==='\n'||c==='\r'){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);if(row.some(v=>v!==''))rows.push(row);row=[];cell='';}
  else cell+=c;
 }
 if(quoted)throw Error('The result CSV has an unfinished quoted value.');
 if(cell||row.length){row.push(cell);rows.push(row);}
 const headers=rows.shift()||[];const expected=['batchId','entryId','employee','department','gross','employeeTaxes','deductions','netPay','reimbursement','employerTaxes','employerBenefits','fees'];
 if(JSON.stringify(headers)!==JSON.stringify(expected))throw Error('Use the final-result CSV template. Bank details, SSNs and tax forms are not accepted.');
 return rows.map(row=>{if(row.length!==headers.length)throw Error('A result CSV row has the wrong number of columns.');return Object.fromEntries(headers.map((key,index)=>[key,row[index]]));});
}

export async function mountPayrollManagement({host,user,api,notice}){
 if(!host)return;
 if(!['owner','accountant'].includes(user.role)){host.innerHTML='<h1>Payroll access is restricted</h1>';return;}
 let data,selected='',working=false;
 const owner=user.role==='owner';
 const endpoint=(action,payload)=>api('/api/payroll-management/'+action,payload);
 function profile(id){return data.employees.find(e=>e.id===id);}
 function jobs(id){return profile(id)?.jobs||[];}
 function employeeOptions(){return options(data.employees.map(e=>[e.id,e.name+' · '+e.username+' · '+e.status]));}
 function jobOptions(id){return options(jobs(id).map(j=>[j.id,j.title+' · '+j.division_name+' · '+j.location_name]));}
 const summary=batch=>batch.totals.reduce((sum,r)=>sum+r.grossCents,0);
 async function refresh(){data=await api('/api/payroll-management');if(host.isConnected)render();}
 function render(){
  const batches=data.batches;
  host.innerHTML=`<div class="page-title"><div><div class="eyebrow">PAYROLL PREPARATION</div><h1>Payroll Management</h1><p>Prepare and approve gross wages here. Your external provider calculates final taxes, makes deposits and handles supported filings.</p></div><div class="actions">${owner?'<button data-pm="connect">Connect Employee</button>':''}<button data-pm="sync" ${!data.connection?'disabled':''}>Sync approved Employee hours</button></div></div>
  <section class="panel"><h2>Employee connection</h2><p>${data.connection?'Connected to the reviewed Employee workspace. Last synchronized: '+esc(data.lastSync?.at||'—'):'Connect the existing company owner to Employee to retrieve the roster and approved hours. No Gusto account is required.'}</p>
  ${(data.lastSync?.issues||[]).map(i=>`<p class="amount-negative">${esc(i.start+'–'+i.endExclusive+': '+i.message)}</p>`).join('')}
  ${(data.lastSync?.missingEmployeeIds||[]).length?'<p class="amount-negative">Some previously linked Employee profiles are missing from the latest roster. Review their identity before changing payroll links.</p>':''}
  <p class="small muted">Employee owns profiles and original timecards. Manual payroll and rate overrides are financial records; they do not edit attendance or Employee job records.</p></section>
  <div class="actions spaced"><button class="primary" data-pm="prepare" ${!data.employees.length||!data.providers.length?'disabled':''}>Prepare payroll</button>${owner?'<button data-pm="provider">Configure payroll workflow</button><button data-pm="mapping">Map provider employee IDs</button><button data-pm="rate">Record payroll rate override</button>':''}</div>
  <section class="panel"><h2>Payroll batches</h2>${batches.length?table(['Pay period','Pay date','Gross wages','Status',''],batches.map(b=>`<tr><td>${esc(b.starts_on)} to ${esc(b.ends_on)} <small class="muted">end exclusive</small></td><td>${esc(b.pay_date)}</td><td class="amount">${money(summary(b))}</td><td>${esc(b.status.replaceAll('_',' '))}</td><td><button data-pm="open" data-id="${esc(b.id)}">Open batch</button></td></tr>`)):'<p>No payroll batches yet.</p>'}</section>
  <div data-pm-work></div>
  <details class="panel spaced"><summary>Employee roster and compensation source</summary>${table(['Employee','Username','Company / status','Assigned compensation'],data.employees.map(e=>`<tr><td>${esc(e.name)}</td><td>${esc(e.username)}</td><td>${esc(e.company_id)} · ${esc(e.status)}</td><td>${e.jobs.map(j=>`${esc(j.division_name)}: ${money(j.rate_cents)} / ${j.pay_type==='salary'?'pay period':'hour'}`).join('<br>')}</td></tr>`))}<p class="small muted">Rate overrides are retained with their effective dates. Approved batches keep their original snapshots when a later rate changes.</p></details>
  <p class="small muted">CSV and Excel review downloads are not provider submissions. Provider-format export requires a verified specification and actual employee IDs. Record provider receipt only after confirmation; record payments only after they occurred.</p>`;
  if(selected)showBatch(selected);
 }
 function work(html){host.querySelector('[data-pm-work]').innerHTML=html;host.querySelector('[data-pm-work]').scrollIntoView({block:'nearest'});}
 function form(title,action,html,submit='Save'){selected='';work(`<section class="panel spaced"><h2>${title}</h2><form data-pm-form="${action}">${html}<div class="actions spaced"><button class="primary">${submit}</button><button type="button" data-pm="close">Cancel</button></div></form></section>`);}
 function employeeJobFields(){const eligible=data.employees.filter(e=>e.jobs.length);return `<div class="form-grid"><label>Employee<select name="employeeId" aria-label="Employee" data-pm-employee required>${options(eligible.map(e=>[e.id,e.name+' · '+e.username+' · '+e.status]))}</select></label><label>Assigned job / department<select name="assignmentId" aria-label="Assigned job / department" data-pm-job required>${jobOptions(eligible[0]?.id)}</select></label></div>`;}
 function manualEntry(disabled=false){
  const first=data.employees.find(e=>e.jobs.length),job=first?.jobs[0];
  return `<fieldset data-pm-entry ${disabled?'disabled':''}><legend>Employee payroll line</legend>${employeeJobFields()}<div class="form-grid"><label>Pay type<select name="payType" aria-label="Pay type"><option value="hourly" ${job?.pay_type!=='salary'?'selected':''}>Hourly</option><option value="salary" ${job?.pay_type==='salary'?'selected':''}>Salary for this period</option></select></label>
  ${amount('rateCents','Hourly rate',job?.pay_type==='hourly'?job.rate_cents/100:0)}${amount('salaryCents','Salary amount for this payroll period',job?.pay_type==='salary'?job.rate_cents/100:0)}${amount('regularMinutes','Regular hours',0)}${amount('overtimeMinutes','Overtime hours',0)}${amount('overtimeRateCents','Approved overtime hourly rate',0)}${amount('paidLeaveMinutes','Approved paid-leave hours',0)}
  ${amount('bonusCents','Bonus',0)}${amount('commissionCents','Commission',0)}${amount('otherEarningsCents','Other gross earnings',0)}${amount('reimbursementCents','Non-wage reimbursement for provider review',0)}${amount('approvedDeductionCents','Planned approved deduction (not tax withholding)',0)}
  ${input('verifiedEmployerCostCents','Verified additional employer-cost estimate (optional)','number','','min="0" step="0.01"')}${input('employerCostReference','Employer-cost source / approval reference (if entered)')}</div><button type="button" data-pm="remove-entry">Remove line</button></fieldset>`;
 }
 function additionEntry(){return `<fieldset data-pm-addition><legend>Additional amounts for approved timecards</legend>${employeeJobFields()}<div class="form-grid">${amount('bonusCents','Bonus',0)}${amount('commissionCents','Commission',0)}${amount('otherEarningsCents','Other gross earnings',0)}${amount('reimbursementCents','Non-wage reimbursement for provider review',0)}${amount('approvedDeductionCents','Approved deduction',0)}${input('overtimeRateCents','Provider / owner-approved adjusted overtime rate (optional)','number','','min="0" step="0.01"')}${input('salaryCents','Reviewed salary amount for this period (salary jobs only, optional)','number','','min="0" step="0.01"')}${input('verifiedEmployerCostCents','Verified additional employer-cost estimate (optional)','number','','min="0" step="0.01"')}${input('employerCostReference','Employer-cost source if entered')}${input('reference','Additions / deduction authorization and overtime review reference','text','','required')}</div><button type="button" data-pm="remove-addition">Remove additions</button></fieldset>`;}
 function prepare(){
  const today=new Date().toLocaleDateString('en-CA'),companies=[...new Set(data.employees.map(e=>e.company_id))];
  form('Prepare payroll','prepare',`<p>Automatic preparation uses only complete approved Employee timesheets and reviewed paid leave. Manual entries require no timecards and never overwrite them.</p><div class="form-grid"><label>Method<select name="method" aria-label="Method" data-pm-method><option value="approved_timecards">Approved Employee timecards</option><option value="manual">Manual payroll</option></select></label><label>Employee company<select name="companyId" aria-label="Employee company">${options(companies.map(id=>[id,id]))}</select></label><label>External payroll workflow<select name="providerId" aria-label="External payroll workflow">${options(data.providers.map(p=>[p.id,p.name]))}</select></label>
   ${input('periodStart','Period start','date',today,'required')}${input('periodEndExclusive','Period end (exclusive)','date',today,'required')}${input('payDate','Pay date','date',today,'required')}<label>Salary pay frequency (when applicable)<select name="frequency" aria-label="Salary pay frequency"><option value="">Select actual verified frequency</option>${options([['weekly','Weekly'],['biweekly','Every two weeks'],['semimonthly','Twice monthly'],['monthly','Monthly']])}</select></label></div>
   <div data-pm-manual hidden><div data-pm-entries>${manualEntry(true)}</div><button type="button" data-pm="add-entry">Add employee / department line</button></div>
   <details data-pm-automatic><summary>Add bonuses, commissions, reimbursements or other reviewed amounts to approved timecards</summary><div data-pm-additions></div><button type="button" data-pm="add-addition">Add additional earnings / deductions</button><p class="small muted">Confirm whether bonuses or commissions change the applicable overtime rate. Original Employee hours stay unchanged.</p></details>
   <div class="actions spaced"><button type="button" data-pm="preview">Calculate preview</button></div><div data-pm-preview></div>`,'Create payroll draft');
  host.querySelector('[data-pm-form]').dataset.requestKey=crypto.randomUUID();
 }
 function batchInput(form){
  const v=value(form),entries=[],additions=[];
  if(v.method==='manual')for(const row of form.querySelectorAll('[data-pm-entry]')){
   const read=name=>row.querySelector(`[name="${name}"]`).value;
   const e={employeeId:read('employeeId'),assignmentId:read('assignmentId'),payType:read('payType')};
   for(const name of ['regularMinutes','overtimeMinutes','paidLeaveMinutes'])e[name]=minutes(read(name));
   for(const name of ['rateCents','overtimeRateCents','salaryCents','bonusCents','commissionCents','otherEarningsCents','reimbursementCents','approvedDeductionCents'])e[name]=dollars(read(name));
   if(read('verifiedEmployerCostCents')!==''){e.verifiedEmployerCostCents=dollars(read('verifiedEmployerCostCents'));e.employerCostReference=read('employerCostReference');}
   entries.push(e);
  }
  if(v.method==='approved_timecards')for(const row of form.querySelectorAll('[data-pm-addition]')){
   const read=name=>row.querySelector(`[name="${name}"]`).value;
   const e={employeeId:read('employeeId'),assignmentId:read('assignmentId'),reference:read('reference')};
   for(const name of ['bonusCents','commissionCents','otherEarningsCents','reimbursementCents','approvedDeductionCents'])e[name]=dollars(read(name));
   for(const name of ['overtimeRateCents','salaryCents','verifiedEmployerCostCents'])if(read(name)!=='')e[name]=dollars(read(name));
   if(e.verifiedEmployerCostCents!==undefined)e.employerCostReference=read('employerCostReference');additions.push(e);
  }
  return {requestKey:form.dataset.requestKey,companyId:v.companyId,method:v.method,providerId:v.providerId,periodStart:v.periodStart,periodEndExclusive:v.periodEndExclusive,payDate:v.payDate,frequency:v.frequency||null,entries,additions};
 }
 function showBatch(id){
  const b=data.batches.find(b=>b.id===id);if(!b)return;selected=id;
  const complete=!['draft','reviewed','cancelled'].includes(b.status),p=b.payload;
  work(`<section class="panel spaced"><h2>Payroll batch</h2><p><strong>${esc(b.status.replaceAll('_',' '))}</strong> · ${esc(b.starts_on)} to ${esc(b.ends_on)} (end exclusive) · Pay date ${esc(b.pay_date)}</p><p class="small muted">Batch ${esc(b.id)} · ${esc(b.company_id)}</p>
   ${table(['Employee / department','Source','Regular / OT / paid leave','Gross wages','Reimbursement','Planned deductions'],p.entries.map(e=>`<tr><td>${esc(e.employee)}<small>${esc(e.department)}</small></td><td>${esc(e.method.replaceAll('_',' '))}${e.rateOverride?'<small>Reviewed payroll rate override</small>':''}</td><td>${(Number(e.calculation.regularMinutes)/60).toFixed(2)} / ${(Number(e.calculation.overtimeMinutes)/60).toFixed(2)} / ${(Number(e.calculation.paidLeaveMinutes)/60).toFixed(2)} h</td><td>${money(e.calculation.grossCents)}</td><td>${money(e.calculation.reimbursementCents)}</td><td>${money(e.calculation.approvedDeductionCents)}</td></tr>`))}
   <h3>Department totals</h3>${table(['Department','Gross wages','Employer labor cost estimate'],b.totals.map(r=>`<tr><td>${esc(r.department)}</td><td>${money(r.grossCents)}</td><td>${r.employerLaborCostCents===null?'Not fully estimated':money(r.employerLaborCostCents)}</td></tr>`))}
   <p><strong>Total gross wages: ${money(summary(b))}</strong>. Taxes and net payments are supplied by the provider.</p>
   ${(p.issues||[]).map(i=>`<p class="small">${esc(i)}</p>`).join('')}
   ${p.review?`<p>Reviewed by ${esc(p.review.by)}: ${esc(p.review.reason)}</p>`:''}
   ${p.approval?`<p>Approved gross accrual by ${esc(p.approval.by)} on ${esc(p.approval.at)}. This did not pay employees.</p>`:''}
   <div class="actions spaced">${['draft','reviewed'].includes(b.status)?'<button data-pm="review" data-id="'+esc(id)+'">Review payroll</button><button data-pm="cancel" data-id="'+esc(id)+'">Cancel draft</button>':''}${b.status==='reviewed'&&owner?'<button class="primary" data-pm="approve" data-id="'+esc(id)+'">Approve gross payroll</button>':''}
   ${complete?`<a class="button" href="/api/payroll-management/export?id=${encodeURIComponent(id)}&format=csv" data-pm-download>Download CSV review</a><a class="button" href="/api/payroll-management/export?id=${encodeURIComponent(id)}&format=xlsx" data-pm-download>Download Excel review</a>${p.providerSnapshot?.verifiedImport?`<a class="button" href="/api/payroll-management/export?id=${encodeURIComponent(id)}&format=provider_csv" data-pm-download>Download verified provider CSV</a>`:''}`:''}
   ${owner&&['approved','exported'].includes(b.status)?'<button data-pm="receipt" data-id="'+esc(id)+'">Record provider receipt</button>':''}
   ${owner&&b.status==='receipt_confirmed'?'<button data-pm="final" data-id="'+esc(id)+'">Record final provider report</button>':''}
   ${owner&&['final_posted','reconciled'].includes(b.status)?'<button data-pm="payment" data-id="'+esc(id)+'">Record actual bank settlement</button><button data-pm="reconcile" data-id="'+esc(id)+'">Check bank reconciliation</button>':''}</div>
   ${complete?'<p class="small muted">Exports remain the approved snapshot. Sending or uploading that file is a separate provider step. Configure provider mappings before approval; general review exports remain available without provider-specific import access.</p>':''}
   ${b.receipt?`<p>Provider receipt confirmed: ${esc(b.receipt.reference)} · ${esc(b.receipt.confirmed_at)}</p>`:''}
   ${b.remaining?`<h3>Actual liabilities remaining</h3>${table(['Net pay','Provider taxes','Deductions','Fees','Benefits'],['<tr>'+Object.values(b.remaining).map(n=>'<td>'+money(n)+'</td>').join('')+'</tr>'])}`:''}
   ${b.payments.length?`<h3>Recorded actual settlements</h3>${table(['Bank reference','Amount','Bank line for reconciliation'],b.payments.map(p=>`<tr><td>${esc(p.reference)}</td><td>${money(p.amount)}</td><td>${p.bank_line_id}</td></tr>`))}<button data-view="reconcile">Open Bank reconciliation</button>`:''}
   <div data-pm-batch-form></div></section>`);
 }
 function batchForm(id,action,title,html,submit){showBatch(id);const slot=host.querySelector('[data-pm-batch-form]');slot.innerHTML=`<h3 class="spaced">${title}</h3><form data-pm-form="${action}" data-id="${esc(id)}">${html}<button class="primary spaced">${submit}</button></form>`;slot.scrollIntoView({block:'nearest'});}
 function provider(){form('External payroll workflow','provider',`<p>No direct provider API is configured. Use HR.my, ADP or another provider externally. These settings map identifiers and earnings; they do not transmit payroll.</p><div class="form-grid"><label>Provider identifier<select name="id" aria-label="Provider identifier"><option value="hrmy">hrmy</option><option value="adp">adp</option><option value="external">other external provider</option></select></label>${input('name','Workflow name','text','HR.my external workflow','required')}</div>
   <h3>Earnings codes (enter actual provider codes only)</h3><div class="form-grid">${['regular','overtime','bonus','commission','other','leave','reimbursement','deduction'].map(k=>input('code_'+k,k+' code')).join('')}</div>
   <details><summary>Verified CSV import specification</summary><p class="small muted">Leave this unverified until you have the provider’s actual approved import layout. General CSV/Excel review exports work without it.</p>${input('specification','Provider import specification / reference')}<label><input type="checkbox" name="verifiedImport"> I verified this provider import layout</label>
   <div class="form-grid">${['providerEmployeeId','regularHours','overtimeHours','paidLeaveHours','hourlyRate','overtimeRate','salary','bonus','commission','otherEarnings','reimbursement','approvedDeductions','grossPay','payDate','periodStart','periodEndExclusive','regularCode','overtimeCode','bonusCode','commissionCode','otherCode','leaveCode','reimbursementCode','deductionCode'].map(k=>input('column_'+k,'Exact CSV column for '+k+' (blank omits it)')).join('')}</div></details>`,'Save workflow');}
 host.addEventListener('change',async event=>{
  if(event.target.matches('[data-pm-final-file]')){
   try{
    const file=event.target.files[0];if(!file)return;if(file.size>1024*1024)throw Error('Result CSV exceeds 1 MB.');
    const form=event.target.form,batch=data.batches.find(b=>b.id===form.dataset.id),rows=parseResultCsv(await file.text());
    if(rows.length!==batch.payload.entries.length)throw Error('Include exactly one result row per prepared payroll line.');
    const seen=new Set(),updates=[];
    for(const row of rows){
     const e=batch.payload.entries.find(e=>e.id===row.entryId);
     if(row.batchId!==batch.id||!e||seen.has(e.id)||row.employee!==safeCsvIdentity(e.employee)||row.department!==safeCsvIdentity(e.department))throw Error('The result CSV belongs to a different batch or employee / department.');
     seen.add(e.id);for(const key of ['gross','employeeTaxes','deductions','netPay','reimbursement','employerTaxes','employerBenefits','fees']){dollars(row[key]);updates.push([e.id,key+'Cents',row[key]]);}
    }
    for(const [id,name,v] of updates)form.querySelector(`[data-pm-final-entry][data-entry="${CSS.escape(id)}"] [name="${name}"]`).value=v;
    notice('Actual result amounts loaded for review. Confirm the provider report before posting.');
   }catch(error){notice(error.message,true);}
  }
  if(event.target.matches('[data-pm-method]')){const automatic=event.target.value!=='manual';host.querySelector('[data-pm-manual]').hidden=automatic;host.querySelector('[data-pm-automatic]').hidden=!automatic;for(const entry of host.querySelectorAll('[data-pm-entry]'))entry.disabled=automatic;for(const entry of host.querySelectorAll('[data-pm-addition]'))entry.disabled=!automatic;}
  if(event.target.matches('[data-pm-employee]')){
   const scope=event.target.closest('[data-pm-entry],[data-pm-addition]')||event.target.form;scope.querySelector('[data-pm-job]').innerHTML=jobOptions(event.target.value);
  }
  if(event.target.matches('[data-pm-employee],[data-pm-job]')){
   const row=event.target.closest('[data-pm-entry]');if(row){const e=profile(row.querySelector('[name=employeeId]').value),j=e.jobs.find(j=>j.id===row.querySelector('[name=assignmentId]').value);if(j){row.querySelector('[name=rateCents]').value=j.pay_type==='hourly'?j.rate_cents/100:0;row.querySelector('[name=payType]').value=j.pay_type;row.querySelector('[name=salaryCents]').value=j.pay_type==='salary'?j.rate_cents/100:0;}}
  }
 });
 host.addEventListener('click',async event=>{
  const download=event.target.closest('a[data-pm-download]');
  if(download){
   event.preventDefault();
   try{
    const response=await fetch(download.href);if(!response.ok){const error=await response.json();throw Error(error.error||'The approved export is not ready.');}
    const url=new URL(download.href),format=url.searchParams.get('format');
    // Android saves authenticated HTTP attachments through its native picker.
    // A blob: URL cannot be fetched by that picker. The export is immutable and
    // idempotent, so validate first and download the same authorized URL.
    await response.body?.cancel();
    const a=document.createElement('a');
    a.href=download.href;a.download='backwoods-payroll-'+(format==='final_template'?'final-result-template':'review')+'-'+url.searchParams.get('id')+'.'+(format==='xlsx'?'xlsx':'csv');document.body.append(a);a.click();a.remove();
    notice('Approved file opened for saving. This did not submit payroll or record a payment.');
   }catch(error){notice(error.message,true);}
   return;
  }
  const button=event.target.closest('[data-pm]');if(!button||working)return;
  try{
   const action=button.dataset.pm,id=button.dataset.id,b=data.batches.find(b=>b.id===id);
   if(action==='close'){selected='';work('');}
   if(action==='prepare')prepare();
   if(action==='open')showBatch(id);
   if(action==='provider')provider();
   if(action==='add-entry')host.querySelector('[data-pm-entries]').insertAdjacentHTML('beforeend',manualEntry());
   if(action==='remove-entry')button.closest('[data-pm-entry]').remove();
   if(action==='add-addition')host.querySelector('[data-pm-additions]').insertAdjacentHTML('beforeend',additionEntry());
   if(action==='remove-addition')button.closest('[data-pm-addition]').remove();
   if(action==='preview'){
    const result=await endpoint('preview',batchInput(button.closest('form')));host.querySelector('[data-pm-preview]').innerHTML=`<h3>Gross payroll preview: ${money(result.entries.reduce((s,e)=>s+e.calculation.grossCents,0))}</h3>${result.issues.map(i=>'<p>'+esc(i)+'</p>').join('')}<p class="small muted">No payroll batch, provider submission or financial posting was created by this preview.</p>`;
   }
   if(action==='sync'){await endpoint('sync',{});notice('Approved Employee roster and hours synchronized.');await refresh();}
   if(action==='connect'){
    const preview=await endpoint('employee-preview',{});form('Connect the existing Employee workspace','employee-connect',`<p>${preview.employees} employees · ${preview.approvedPackets} approved time packets.</p><p>${esc(preview.companies.map(c=>c.name+' ('+c.id+')').join(', '))}</p><label>Employee legal company for these Accounting books<select name="companyId" aria-label="Employee legal company" required>${options(preview.companies.map(c=>[c.id,c.name+' ('+c.id+')']))}</select></label><input type="hidden" name="workspace" value="${esc(preview.workspace)}">${check('confirmed','I reviewed this actual Employee workspace and company mapping.')}`,'Connect and synchronize');
   }
   if(action==='mapping')form('Map an existing Employee to the payroll provider','mapping',`<label>Workflow<select name="providerId" aria-label="External payroll workflow">${options(data.providers.map(p=>[p.id,p.name]))}</select></label><label>Employee<select name="employeeId" aria-label="Employee">${employeeOptions()}</select></label>${input('providerEmployeeId','Actual provider employee identifier','text','','required')}`);
   if(action==='rate')form('Record a payroll compensation override','rate',`${employeeJobFields()}<div class="form-grid">${input('effectiveDate','Effective date','date','','required')}<label>Pay type<select name="payType" aria-label="Pay type"><option value="hourly">Hourly</option><option value="salary">Salary amount per pay period</option></select></label>${amount('rateCents','Hourly rate / explicit salary amount for one pay period')}${amount('overtimeRateCents','Approved overtime hourly rate',0)}</div>${input('reason','Actual compensation approval reference','text','','required')}${check('reviewed','I verified this compensation, salary basis if applicable, and effective date.')}<p class="small muted">This keeps a financial override history. For a permanent employment-rate change, update the job in Employee too; existing approved batches and original timecards stay unchanged.</p>`);
   if(action==='review')batchForm(id,'review','Review payroll',`${check('reviewed','I reviewed each employee, department, rate, additions and planned deductions.')}${check('overtimeReviewed','I verified the applicable workweek / overtime rules, hour allocation and salary classification.')}${input('reason','Review reference / explanation','text','','required')}`,'Save payroll review');
   if(action==='approve')batchForm(id,'approve','Approve gross payroll',`${check('confirmed','Approve this exact gross-wage batch and record its gross payroll accrual. This does not submit payroll or pay staff.')}`,'Approve gross payroll');
   if(action==='cancel')batchForm(id,'cancel','Cancel this unapproved draft',input('reason','Reason','text','','required'),'Cancel draft');
   if(action==='receipt')batchForm(id,'receipt','Record confirmed provider receipt',`${input('reference','Actual provider receipt reference','text','','required')}${input('evidence','Provider confirmation / evidence','text','','required')}${check('providerConfirmed','The external provider actually confirmed receipt of this batch. A downloaded export alone is not confirmation.')}`,'Record provider receipt');
   if(action==='final')batchForm(id,'final-report','Actual final provider report',`<p><a href="/api/payroll-management/export?id=${encodeURIComponent(id)}&format=final_template" data-pm-download>Download final-result CSV template</a></p><label>Import completed result CSV (amounts in dollars)<input type="file" data-pm-final-file accept=".csv,text/csv"></label><p>Enter actual provider totals for each employee and department. Tax, deduction and net amounts are required, including actual zeros. The app does not calculate statutory withholding.</p>${b.payload.entries.map(e=>`<fieldset data-pm-final-entry data-entry="${esc(e.id)}"><legend>${esc(e.employee)} · ${esc(e.department)} · prepared gross ${money(e.calculation.grossCents)}</legend><div class="form-grid">${[['grossCents','Actual gross wages'],['employeeTaxesCents','Actual employee taxes / withholding'],['deductionsCents','Actual other deductions'],['reimbursementCents','Actual non-wage reimbursements'],['netPayCents','Actual net payment including reimbursements'],['employerTaxesCents','Actual employer taxes'],['employerBenefitsCents','Actual employer benefits'],['feesCents','Actual provider processing fees']].map(([key,label])=>amount(key,label)).join('')}</div></fieldset>`).join('')}${input('reference','Final provider report reference','text','','required')}${input('postingDate','Accounting posting date','date',b.pay_date,'required')}${input('varianceReason','Explain any wage / deduction / reimbursement or posting-date variance')}${check('actualProviderReport','These figures come from the actual final provider report, and I verified its employee / department allocation.')}`,'Post actual final report');
   if(action==='payment')batchForm(id,'payment','Record a payment that already occurred',`<p>This records the bank settlement; it does not send money. Link an existing bank line when it is already in your books.</p><label>Bank record<select name="bankMode" aria-label="Bank record"><option value="existing">Link an existing bank credit line</option><option value="new">Record an actual payment not yet in the ledger</option></select></label>${input('bankLineId','Existing bank credit line ID (required when linking)','number','','min="1"')}<div class="form-grid">${Object.keys(b.remaining).map(k=>amount(k,'Actual '+k+' paid',0)).join('')}</div>${input('date','Actual settlement / posting date','date','','required')}${input('reference','Actual bank transaction / settlement reference','text','','required')}<label><input type="checkbox" name="reclassifyExpense"> Reclassify this existing, unreconciled bank expense to payroll liabilities</label>${input('reason','Reason for any expense reclassification')}${check('actualPayment','I verified this payment actually occurred and is not being recorded twice.')}`,'Record actual settlement');
   if(action==='reconcile'){await endpoint('reconcile',{id});notice('All actual payroll liabilities and bank lines are reconciled.');await refresh();showBatch(id);}
  }catch(error){notice(error.message,true);}
 });
 host.addEventListener('submit',async event=>{
  const form=event.target.closest('[data-pm-form]');if(!form)return;event.preventDefault();if(working||!form.reportValidity())return;
  working=true;const action=form.dataset.pmForm;let payload=value(form);if(form.dataset.id)payload.id=form.dataset.id;
  const submit=form.querySelector('button[type=submit],button.primary');if(submit)submit.disabled=true;
  try{
   for(const key of ['reviewed','overtimeReviewed','confirmed','providerConfirmed','actualProviderReport','actualPayment','reclassifyExpense','verifiedImport'])if(field(form,key))payload[key]=field(form,key).checked;
   if(action==='prepare')payload=batchInput(form);
   if(action==='rate'){payload.rateCents=dollars(payload.rateCents);payload.overtimeRateCents=dollars(payload.overtimeRateCents);}
   if(action==='provider'){
    payload.earningCodes={};payload.csvColumns={};for(const [key,v] of Object.entries(payload)){if(key.startsWith('code_')&&v)payload.earningCodes[key.slice(5)]=v;if(key.startsWith('column_')&&v)payload.csvColumns[key.slice(7)]=v;}
   }
   if(action==='final-report'){
    payload.entries=[];for(const row of form.querySelectorAll('[data-pm-final-entry]')){const entry={entryId:row.dataset.entry};for(const input of row.querySelectorAll('input'))entry[input.name]=dollars(input.value);payload.entries.push(entry);}
    for(const key of ['grossCents','employeeTaxesCents','deductionsCents','reimbursementCents','netPayCents','employerTaxesCents','employerBenefitsCents','feesCents'])delete payload[key];
   }
   if(action==='payment'){
    payload.allocations={};for(const key of ['netPay','taxes','deductions','fees','benefits']){const n=dollars(payload[key]);if(n)payload.allocations[key]=n;delete payload[key];}
    if(payload.bankMode==='existing'){if(!payload.bankLineId)throw Error('Enter the existing bank credit line ID.');payload.bankLineId=Number(payload.bankLineId);}else delete payload.bankLineId;delete payload.bankMode;
   }
   const result=await endpoint(action,payload);notice(action==='prepare'?'Payroll draft prepared. Review before approval.':'Payroll record saved.');selected=result.id||form.dataset.id||'';data=await api('/api/payroll-management');working=false;if(host.isConnected)render();
  }catch(error){notice(error.message,true);}
  finally{working=false;if(submit?.isConnected)submit.disabled=false;}
 });
 await refresh();
}
