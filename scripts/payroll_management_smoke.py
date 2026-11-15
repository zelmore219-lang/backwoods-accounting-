"""Actual Accounting UI with fictional payroll, no external provider/bank calls."""
import csv,io,json,shutil,sys,tempfile,threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from accounting.server import Application,Handler
from accounting import payroll_management as pm,auth
from test_payroll_management import roster

def run():
 output=ROOT/'test-results/payroll-management';output.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory() as folder:
  app=Application(folder);ledger=app.ledger();pm.sync_employees(ledger,'existing-workspace-001',roster(),confirm=True);ledger.close()
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.application=app
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();origin='http://127.0.0.1:'+str(server.server_port)
  try:
   with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
    try:
     context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page();page.set_default_timeout(18000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin) else route.abort())
     page.goto(origin);form=page.locator('#login-form');form.locator('[name=name]').fill('Fictional Payroll Owner');form.locator('[name=username]').fill('payroll.owner');form.locator('[name=password]').fill('fictional-payroll-passphrase');form.locator('[name=confirmPassword]').fill('fictional-payroll-passphrase');form.get_by_role('button',name='Create owner account').click()
     page.get_by_role('button',name='Payroll Management',exact=True).click();expect(page.get_by_role('heading',name='Payroll Management',exact=True)).to_be_visible()
     page.get_by_role('button',name='Configure payroll workflow',exact=True).click();page.get_by_role('button',name='Save workflow',exact=True).click()
     page.get_by_role('button',name='Prepare payroll',exact=True).click();page.screenshot(path=str(output/'prepare-debug.png'),full_page=True);(output/'prepare-debug.txt').write_text(page.locator('body').inner_text());(output/'prepare-errors.json').write_text(json.dumps(errors));form=page.locator('[data-pm-form=prepare]')
     form.get_by_label('Method',exact=True).select_option('manual');form.get_by_label('Period start',exact=True).fill('2026-10-19');form.get_by_label('Period end (exclusive)',exact=True).fill('2026-10-26');form.get_by_label('Pay date',exact=True).fill('2026-10-30')
     form.get_by_label('Regular hours',exact=True).fill('40');form.get_by_label('Overtime hours',exact=True).fill('5');form.get_by_label('Approved overtime hourly rate',exact=True).fill('22.50');form.get_by_label('Bonus',exact=True).fill('50')
     form.get_by_role('button',name='Calculate preview',exact=True).click();expect(page.locator('[data-pm-preview]')).to_contain_text('$762.50')
     ledger=app.ledger();assert not ledger.rows();ledger.close()
     form.get_by_role('button',name='Create payroll draft',exact=True).click();expect(page.get_by_role('heading',name='Payroll batch',exact=True)).to_be_visible()
     page.get_by_role('button',name='Review payroll',exact=True).click();form=page.locator('[data-pm-form=review]');form.locator('[name=reviewed]').check();form.locator('[name=overtimeReviewed]').check();form.get_by_label('Review reference / explanation',exact=True).fill('Fictional owner reviewed original hours and approved overtime rate');form.get_by_role('button',name='Save payroll review').click()
     page.get_by_role('button',name='Approve gross payroll',exact=True).click();form=page.locator('[data-pm-form=approve]');form.locator('[name=confirmed]').check();form.get_by_role('button',name='Approve gross payroll',exact=True).click()
     page.get_by_role('link',name='Download Excel review',exact=True).wait_for()
     with page.expect_download() as download:page.get_by_role('link',name='Download Excel review',exact=True).click()
     excel=download.value;excel.save_as(output/'fictional-payroll-review.xlsx')
     page.get_by_role('button',name='Record provider receipt',exact=True).click();form=page.locator('[data-pm-form=receipt]');form.get_by_label('Actual provider receipt reference',exact=True).fill('FIXTURE-RECEIPT-UI');form.get_by_label('Provider confirmation / evidence',exact=True).fill('Fictional provider acknowledgement for isolated UI testing only');form.locator('[name=providerConfirmed]').check();form.get_by_role('button',name='Record provider receipt',exact=True).click()
     page.get_by_role('button',name='Record final provider report',exact=True).click();form=page.locator('[data-pm-form=final-report]')
     with page.expect_download() as download:form.get_by_role('link',name='Download final-result CSV template').click()
     template=download.value;path=output/'fictional-final-template.csv';template.save_as(path)
     rows=list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))));assert len(rows)==1
     rows[0].update(gross='762.50',employeeTaxes='100',deductions='0',netPay='662.50',reimbursement='0',employerTaxes='50',employerBenefits='0',fees='2.50')
     result=io.StringIO(newline='');writer=csv.DictWriter(result,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows);path=output/'fictional-provider-final.csv';path.write_text(result.getvalue())
     form.locator('[data-pm-final-file]').set_input_files(path);expect(form.get_by_label('Actual net payment including reimbursements',exact=True)).to_have_value('662.50')
     form.get_by_label('Final provider report reference',exact=True).fill('FIXTURE-REPORT-UI');form.locator('[name=actualProviderReport]').check();form.get_by_role('button',name='Post actual final report').click()
     page.get_by_role('button',name='Record actual bank settlement',exact=True).click();form=page.locator('[data-pm-form=payment]');form.get_by_label('Bank record',exact=True).select_option('new')
     for key,amount in [('netPay','662.50'),('taxes','150'),('fees','2.50')]:form.locator('[name='+key+']').fill(amount)
     form.get_by_label('Actual settlement / posting date',exact=True).fill('2026-10-30');form.get_by_label('Actual bank transaction / settlement reference',exact=True).fill('FIXTURE-BANK-UI');form.locator('[name=actualPayment]').check();form.get_by_role('button',name='Record actual settlement',exact=True).click()
     expect(page.get_by_role('heading',name='Recorded actual settlements',exact=True)).to_be_visible()
     ledger=app.ledger();batch=ledger.db.execute('SELECT id FROM pm_batches').fetchone()[0];bank=ledger.db.execute('SELECT bank_line_id FROM pm_payments').fetchone()[0]
     assert ledger.report()['profit']==-81500;assert not any(pm.remaining(ledger,batch).values());ledger.close()
     response=page.request.post(origin+'/api/reconcile',headers={'X-Accounting-Request':'1'},data={'account':'1020','date':'2026-10-31','starting':'0','ending':'-815','lineIds':[bank]});assert response.ok,response.text()
     page.get_by_role('button',name='Check bank reconciliation',exact=True).click();expect(page.locator('[data-pm-work]')).to_contain_text('reconciled')
     page.screenshot(path=str(output/'payroll-reconciled-desktop.png'),full_page=True)
     ledger=app.ledger();before=ledger.rows();payment=json.loads(ledger.db.execute('SELECT payload FROM pm_payments').fetchone()[0]);final=json.loads(ledger.db.execute('SELECT payload FROM pm_final_reports').fetchone()[0]);ledger.close()
     for action,payload in [('payment',payment),('final-report',final)]:
      response=page.request.post(origin+'/api/payroll-management/'+action,headers={'X-Accounting-Request':'1'},data=payload);assert response.ok,response.text()
     ledger=app.ledger();assert ledger.rows()==before;assert ledger.db.execute('SELECT COUNT(*) FROM pm_payments').fetchone()[0]==1
     auth.create_user(ledger,{'username':'financial.viewer','name':'Fictional Viewer','password':'fictional-viewer-passphrase','role':'viewer'});ledger.close()
     for width,height in [(900,1200),(390,844)]:page.set_viewport_size({'width':width,'height':height});page.screenshot(path=str(output/('payroll-reconciled-'+str(width)+'.png')),full_page=True)
     response=page.request.post(origin+'/api/auth/logout',headers={'X-Accounting-Request':'1'},data={});assert response.ok
     page.reload();form=page.locator('#login-form');form.locator('[name=username]').fill('financial.viewer');form.locator('[name=password]').fill('fictional-viewer-passphrase');form.get_by_role('button',name='Sign in',exact=True).click();expect(page.get_by_role('heading',name='Your business, all together.',exact=True)).to_be_visible()
     assert not page.get_by_role('button',name='Payroll Management',exact=True).is_visible()
     for endpoint in ['/api/payroll-management','/api/payroll-management/export?id='+batch+'&format=csv']:
      response=page.request.get(origin+endpoint);assert response.status==403,response.text()
     assert not errors,errors
     context.close()
    finally:browser.close()
  finally:server.shutdown();server.server_close();app.stop.set();thread.join(timeout=10)
 print('PASS: real Payroll Management UI, $762.50 manual gross, owner review/accrual, Excel export, actual-result CSV import, final accounting, settlement/bank reconciliation, duplicate retry, responsive screens and viewer denial. No provider or bank calls.')
if __name__=='__main__':run()
