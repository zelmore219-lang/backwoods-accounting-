"""Actual Accounting connection UI; private-feed fixture, no live company access."""
import json,shutil,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from accounting.server import Application,Handler
from accounting import payroll_management as pm,auth
from test_payroll_management import roster
from test_pest import packet
def run():
 output=ROOT/'test-results/pest-connection';output.mkdir(parents=True,exist_ok=True)
 payload=roster();payload['pestAccounting']=[packet()]
 with tempfile.TemporaryDirectory() as directory:
  app=Application(directory);ledger=app.ledger();pm.sync_employees(ledger,'pest-ui-workspace-001',payload,confirm=True);ledger.close()
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.application=app;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();origin='http://127.0.0.1:'+str(server.server_port)
  try:
   with patch.object(pm,'employee_feed',return_value=('pest-ui-workspace-001',payload)),sync_playwright() as p:
    browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
    try:
     page=browser.new_page(viewport={'width':1400,'height':1000});page.set_default_timeout(15000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin) else route.abort())
     page.goto(origin);form=page.locator('#login-form');form.locator('[name=name]').fill('Fictitious Pest Finance Owner');form.locator('[name=username]').fill('pest.finance');form.locator('[name=password]').fill('fictional-finance-passphrase');form.locator('[name=confirmPassword]').fill('fictional-finance-passphrase');form.get_by_role('button',name='Create owner account').click()
     page.get_by_role('button',name='App connections',exact=True).click();page.get_by_role('button',name='Connect Pest Control',exact=True).click();form=page.locator('#pest-accounting-confirm');expect(form).to_contain_text('same legal company');form.locator('[name=confirmed]').check();form.get_by_role('button',name='Connect and import',exact=True).click()
     expect(page.locator('#content')).to_contain_text('Connected to this legal company · department Pest Control.')
     page.get_by_role('button',name='Review Pest Control connection',exact=True).click();form=page.locator('#pest-accounting-confirm');form.locator('[name=confirmed]').check();form.get_by_role('button',name='Connect and import',exact=True).click();expect(page.locator('#content')).to_contain_text('Connected to this legal company')
     page.screenshot(path=str(output/'pest-connected-desktop.png'),full_page=True)
     ledger=app.ledger();assert ledger.db.execute("SELECT COUNT(*) FROM documents WHERE source='pest'").fetchone()[0]==2;balances={r['code']:r['balance'] for r in ledger.report()['trial']};assert balances['1100']==6800 and balances['1030']==4000;ledger.close()
     page.get_by_role('button',name='Company ledger',exact=True).click();page.locator('[name=source]').select_option('pest');page.get_by_role('button',name='Apply',exact=True).click();expect(page.locator('#content')).to_contain_text('Pest Control')
     for width,height in [(900,1200),(390,844)]:page.set_viewport_size({'width':width,'height':height});page.screenshot(path=str(output/('pest-ledger-'+str(width)+'.png')),full_page=True)
     assert not errors,errors;page.close()
    finally:browser.close()
  finally:server.shutdown();server.server_close();app.stop.set();thread.join(timeout=10)
 print('PASS: actual owner App connections → Pest preview/confirmation/import, same-company department, source filter, responsive ledger and duplicate protection. Fixture private feed; no live payments or business records changed.')
if __name__=='__main__':run()
