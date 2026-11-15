"""Exercise the existing Production packaging screens and background handoff."""
import argparse,json,os
from pathlib import Path
from playwright.sync_api import sync_playwright
p=argparse.ArgumentParser();p.add_argument('--origin',required=True);p.add_argument('--output',required=True);p.add_argument('--package-only',action='store_true');args=p.parse_args()
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
errors=[];checks=[]
with sync_playwright() as browser_api:
 browser=browser_api.chromium.launch(executable_path=os.environ.get('PRODUCTION_CHROMIUM','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
 context=browser.new_context();page=context.new_page();page.on('pageerror',lambda e:(errors.append(str(e)),print('Browser page error:',e,flush=True)))
 page.goto(args.origin);page.get_by_role('heading',name='Sign in',exact=True).wait_for()
 page.get_by_label('Username',exact=True).fill('emulator.owner');page.get_by_label('Password (12+ characters)',exact=True).fill('emulator-owner-passphrase')
 page.get_by_role('button',name='Continue',exact=True).click();page.get_by_role('heading',name='What are you working on?').wait_for()
 if args.package_only:
  page.get_by_role('button',name='Package & release',exact=True).first.click()
  page.get_by_role('button',name='Package stock',exact=True).first.click()
  page.get_by_label('Packaged product SKU',exact=True).fill('PEA-8')
  page.get_by_label('New packaged lot',exact=True).fill('FIN-1')
  page.get_by_label('Package count',exact=True).fill('16')
  page.get_by_label('Net weight per bag (oz)',exact=True).fill('8')
  page.get_by_role('button',name='Save record',exact=True).click();page.locator('#modal').wait_for(state='hidden')
  page.get_by_role('button',name='Inspect this lot',exact=True).click()
  page.locator('#fields [name="status"]').select_option('Approved')
  page.get_by_label('Inspection findings and release notes',exact=True).fill('Checked actual packaged lot')
  page.get_by_role('button',name='Save record',exact=True).click();page.locator('#modal').wait_for(state='hidden')
  page.get_by_role('button',name='Release for sale',exact=True).click()
  page.get_by_label('Inspection findings and release notes',exact=True).fill('Packaged and ready for sale')
  page.get_by_role('button',name='Save record',exact=True).click();page.locator('#modal').wait_for(state='hidden')
  page.screenshot(path=str(out/'original-packaging-workflow.png'),full_page=True)
  checks.append('original packaging, inspection and release forms')
 else:
  for label,width,height in [('desktop',1440,1000),('tablet',820,1180),('phone',390,844)]:
   page.set_viewport_size({'width':width,'height':height})
   page.get_by_role('button',name='Overview',exact=True).click();page.get_by_role('heading',name='What are you working on?').wait_for()
   page.screenshot(path=str(out/(label+'-original-production.png')),full_page=True)
   page.get_by_role('button',name='Ready to sell',exact=True).first.click();page.get_by_role('heading',name='Ready to sell',exact=True).wait_for()
   assert page.get_by_role('button',name='Reserve stock',exact=True).count()==0
   assert page.get_by_role('heading',name='Assigned to Vendor',exact=True).count()==0
   page.screenshot(path=str(out/(label+'-cleared-production-stock.png')),full_page=True)
   if not page.get_by_role('button',name='Connections',exact=True).is_visible():page.get_by_text('Manager tools',exact=True).click()
   page.get_by_role('button',name='Connections',exact=True).click();page.get_by_role('heading',name='Connections',exact=True).wait_for()
   page.get_by_text('Wholesale Vendor Ordering · Transfers received; inventory tracked in Vendor',exact=True).wait_for()
   assert page.get_by_role('button',name='Match a finished SKU',exact=True).count()==0
   page.get_by_role('button',name='Integration queue',exact=True).click();page.get_by_text('Received by Vendor',exact=True).wait_for()
   page.get_by_role('button',name='Production',exact=True).click();page.get_by_text('FIN-1',exact=True).wait_for()
   overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')
   assert not overflow,(label,'horizontal page overflow')
   checks.append(label)
 assert not errors,errors
 context.close();browser.close()
print(json.dumps({'checks':checks,'pageErrors':errors,'originalProductionScreens':True,'packagedStockClearedAfterTransfer':not args.package_only}))
