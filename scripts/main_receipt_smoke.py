"""Exercise the actual Main bundle in Chromium with isolated local test records.

Firebase Auth is deliberately mocked unavailable; no live customer records or
credentials are used. The normal app login, POS, persistence, inventory, receipt
queue and accounting export run unchanged.
"""
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import threading
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results/main-receipts'
PASSWORD='Receipt-test-only-4831!'
USER={'id':991,'username':'receipt-test','displayName':'Receipt Test Cashier','role':'owner','employeeId':991,'storeId':1,'active':True,
      'passwordHash':hashlib.sha256(('receipt-test-salt:'+PASSWORD).encode()).hexdigest(),'passwordSalt':'receipt-test-salt','passwordVersion':'sha256-v1'}
DATA={'settings':{'businessName':'Backwoods Brew','setupCompleted':True,'activeStoreId':1,'taxRate':10},
      'stores':[{'id':1,'name':'Oxford Test Store','address':'123 Test Street'}],
      'storeSettings':[{'storeId':1,'taxRate':10,'priceMultiplier':1}],
      'users':[USER],'employees':[{'id':991,'name':'Receipt Test Cashier','username':'receipt-test','storeId':1,'active':True}],
      'products':[{'id':'test-latte','name':'Receipt Test Latte','price':5,'category':'Hot','storeId':1}],
      'drinkSizes':[{'id':'medium','name':'Medium','label':'16 oz','priceAdd':0,'recipeScale':1}],
      'menuRecipes':{'test-latte':[{'inventoryId':'test-beans','qty':0.05}]},
      'inventory':[{'id':'test-beans','item':'Test Coffee Beans','qty':20,'low':1,'unit':'lb','cost':10,'storeId':1}],
      'orders':[],'bills':[],'expenses':[],'journalEntries':[],'wholesaleSentinel':{'preserve':'unchanged'}}

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT/'source-app-updates/main/www')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    origin=f'http://127.0.0.1:{server.server_port}/'
    try:
        with sync_playwright() as p:
            options={'args':['--no-sandbox']}
            executable=shutil.which('chromium') or shutil.which('google-chrome')
            if executable:options['executable_path']=executable
            browser=p.chromium.launch(**options)
            for native in [False,True]:
                context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='America/Chicago')
                seed={'backwoods-brew-stable-data':json.dumps(DATA),'backwoods-brew-stable-users':json.dumps([USER]),
                      'backwoods-wholesale-v82-v1':json.dumps({'sentinel':'historical records retained'})}
                context.add_init_script('if(window===window.top)for(const [key,value] of Object.entries('+json.dumps(seed)+'))localStorage.setItem(key,value);window.__testPrints=[];window.__testPopups=0;window.open=()=>{window.__testPopups++;return null};window.print=()=>{(window.parent.__testPrints||window.__testPrints).push("browser-print")};'+
                    ('window.backwoodsElectron={printReceipt:async payload=>{window.__testPrints.push(payload);return {ok:false,error:"cancelled"}}};' if native else ''))
                page=context.new_page();page.set_default_timeout(12000);errors=[];dialogs=[];confirmation={'customer':True}
                page.on('pageerror',lambda e:errors.append(str(e)))
                def dialog(d):
                    dialogs.append(d.message)
                    if d.type=='confirm':d.accept() if 'customer receipt' in d.message and confirmation['customer'] else d.dismiss()
                    else:d.accept()
                page.on('dialog',dialog)
                def route(r):
                    if r.request.url.startswith(origin):r.continue_()
                    elif 'identitytoolkit.googleapis.com' in r.request.url:r.fulfill(status=400,content_type='application/json',body=json.dumps({'error':{'code':400,'message':'CONFIGURATION_NOT_FOUND'}}))
                    else:r.abort()
                page.route('**/*',route)
                try:
                    page.goto(origin)
                    page.get_by_placeholder('Username',exact=True).fill('receipt-test')
                    page.get_by_placeholder('Password',exact=True).fill(PASSWORD)
                    page.get_by_role('button',name='Login',exact=True).click()
                    page.get_by_role('button',name='POS Register',exact=True).wait_for(timeout=15000)
                    for text in ['Central Accounting','Wholesale Management']:assert page.get_by_role('button',name=text,exact=True).count()==0,text
                    page.get_by_role('heading',name='Owner Portal',exact=True).wait_for()
                    if not page.get_by_role('button',name='POS Register',exact=True).is_visible():page.get_by_role('button',name=re.compile(r'SALES \+ CLOSEOUT',re.I)).click()
                    page.get_by_role('button',name='POS Register',exact=True).click()
                    page.get_by_role('heading',name='Receipt Test Latte',exact=True).locator('..').get_by_role('button',name='Add',exact=True).click()
                    page.screenshot(path=str(OUT/'register-debug.png'))
                    (OUT/'register-text.txt').write_text(page.locator('main').inner_text())
                    # The register keeps payment inputs in the cart; selectors are actual labels/placeholders.
                    page.locator('label').filter(has_text=re.compile('^Cash Amount Tendered$')).locator('xpath=following-sibling::input[1]').fill('10')
                    page.get_by_role('button',name=re.compile('^Complete .* Sale$',re.I)).click()
                    preview=page.get_by_role('dialog',name='Receipt preview');preview.wait_for()
                    text=preview.locator('pre').inner_text()
                    saved=page.evaluate("JSON.parse(localStorage.getItem('backwoods-brew-stable-data'))")
                    order=saved['orders'][-1]
                    for value in ['Backwoods Brew','Oxford Test Store','Receipt Test Latte','1 x $5.00 = $5.00','Cashier: Receipt Test Cashier','TOTAL: $5.50','Tendered: $10.00','Change: $4.50',str(order['id'])]:assert value in text,(value,text)
                    assert len(saved['orders'])==1
                    assert abs(next(x for x in saved['inventory'] if x['id']=='test-beans')['qty']-19.95)<0.00001
                    await_button=preview.get_by_role('button',name='Print / Save PDF');await_button.click()
                    preview.get_by_role('status').filter(has_text=re.compile('Print options opened|Printing canceled')).wait_for()
                    assert page.evaluate('window.__testPrints.length')>0
                    assert page.evaluate('window.__testPopups')==0
                    if not native:assert page.frame_locator('iframe.bw-receipt-print-frame').locator('pre').inner_text()==text
                    else:assert page.evaluate('window.__testPrints[0].text')==text
                    assert len(page.evaluate("JSON.parse(localStorage.getItem('backwoods-brew-stable-data')).orders"))==1
                    page.screenshot(path=str(OUT/('receipt-native.png' if native else 'receipt-browser.png')))
                    preview.get_by_role('button',name='Close preview').click()
                    page.get_by_role('button',name='Receipts / Printers',exact=True).click()
                    page.get_by_role('button',name='Print Customer Receipt',exact=True).click()
                    assert page.get_by_role('dialog',name='Receipt preview').locator('pre').inner_text()==text
                    export=page.evaluate('window.__bwAccountingSnapshot()')
                    assert export and len(export['data']['orders'])==1
                    journal=export['data']['generalLedger'];assert any(str(order['id']) in str(row.get('source','')) for row in journal)
                    assert abs(sum(row.get('debit',0)-row.get('credit',0) for row in journal))<0.001
                    assert page.evaluate("JSON.parse(localStorage.getItem('backwoods-wholesale-v82-v1')).sentinel")=='historical records retained'
                    page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'receipt-tablet.png'))
                    # Declining a print must still complete exactly one additional sale.
                    page.get_by_role('dialog',name='Receipt preview').get_by_role('button',name='Close preview').click()
                    page.set_viewport_size({'width':1440,'height':1000});confirmation['customer']=False
                    page.get_by_role('button',name='POS Register',exact=True).click()
                    page.get_by_role('heading',name='Receipt Test Latte',exact=True).locator('..').get_by_role('button',name='Add',exact=True).click()
                    page.locator('label').filter(has_text=re.compile('^Cash Amount Tendered$')).locator('xpath=following-sibling::input[1]').fill('10')
                    page.get_by_role('button',name=re.compile('^Complete .* Sale$',re.I)).click()
                    no_print=page.evaluate("JSON.parse(localStorage.getItem('backwoods-brew-stable-data'))")
                    assert len(no_print['orders'])==2
                    assert abs(next(x for x in no_print['inventory'] if x['id']=='test-beans')['qty']-19.90)<0.00001
                    assert page.get_by_role('dialog',name='Receipt preview').count()==0
                    assert page.evaluate('window.__testPopups')==0
                    assert not errors,errors
                    assert not any('popup' in message.lower() for message in dialogs),dialogs
                    (OUT/('native-result.json' if native else 'browser-result.json')).write_text(json.dumps({'passed':True,'transaction':order,'receipt':text,'accountingFeed':export,'liveFirebaseTested':False,'physicalPrinterTested':False},indent=2))
                except Exception:
                    page.screenshot(path=str(OUT/'failure.png'),full_page=True)
                    (OUT/'failure-text.txt').write_text(page.locator('body').inner_text()+'\nERRORS\n'+json.dumps(errors))
                    raise
                finally:context.close()
            browser.close()
    finally:server.shutdown();server.server_close()
    print('PASS: actual Main login/POS transaction, saved inventory and accounting export, complete receipts, browser/Windows bridge printing without popups, cancellation and history reprint.')

if __name__=='__main__':run()
