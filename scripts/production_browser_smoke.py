"""Exercise the actual connected Production renderer using isolated fixture login."""
import argparse,json,os
from pathlib import Path
from playwright.sync_api import sync_playwright
p=argparse.ArgumentParser();p.add_argument('--origin',required=True);p.add_argument('--output',required=True);args=p.parse_args()
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
errors=[];checks=[]
with sync_playwright() as browser_api:
 browser=browser_api.chromium.launch(executable_path=os.environ.get('PRODUCTION_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
 context=browser.new_context();page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(args.origin);page.get_by_role('heading',name='Sign in with Employee/Employer').wait_for()
 page.get_by_label('Username',exact=True).fill('emulator.owner');page.get_by_label('Password (12+ characters)',exact=True).fill('emulator-owner-passphrase')
 page.get_by_role('button',name='Continue',exact=True).click();page.get_by_role('heading',name='What are you working on?').wait_for()
 for label,width,height in [('desktop',1440,1000),('tablet',820,1180),('phone',390,844)]:
  page.set_viewport_size({'width':width,'height':height})
  if not page.get_by_role('button',name='Connections',exact=True).is_visible():page.get_by_text('Manager tools',exact=True).click()
  page.get_by_role('button',name='Connections',exact=True).click();page.get_by_role('heading',name='Connections',exact=True).wait_for()
  page.get_by_text('Received by Vendor',exact=True).wait_for()
  page.get_by_role('button',name='Match a finished SKU',exact=True).click();
  try:page.get_by_label('Vendor product',exact=True).wait_for(timeout=10000)
  except Exception:
   page.screenshot(path=str(out/'mapping-failure.png'),full_page=True)
   print(page.evaluate("({status:document.getElementById('connection-status')?.textContent,form:document.getElementById('mapping-form')?.innerHTML,batches:state.records.filter(b=>b.kind==='batches').map(b=>({sku:b.sku,bulk:b.bulk}))})"),flush=True);raise
  assert page.get_by_label('Vendor product',exact=True).input_value()=='exact-finished-sku'
  assert page.get_by_label('Production SKU',exact=True).input_value()=='PEA-8'
  overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')
  assert not overflow,(label,'horizontal page overflow')
  page.screenshot(path=str(out/(label+'-connections.png')),full_page=True)
  page.get_by_role('button',name='Ready to sell',exact=True).first.click();page.get_by_role('heading',name='Assigned to Vendor',exact=True).wait_for()
  assert page.get_by_role('button',name='Reserve stock',exact=True).count()==0
  page.screenshot(path=str(out/(label+'-vendor-stock.png')),full_page=True)
  checks.append(label)
 assert not errors,errors
 context.close();browser.close()
print(json.dumps({'viewports':checks,'pageErrors':errors,'vendorReceiptVisible':True,'duplicateLocalSaleBlocked':True}))
