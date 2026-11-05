"""Verify Main/Vendor update controls exist only inside Settings."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
import threading
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
MAIN='''<main><div id="settings-card"><div><div><h3>Auto Update</h3><p>Legacy updater</p></div><span>Ready</span></div><div id="legacy-controls"><button>Old check</button></div></div></main>'''
VENDOR='''<main><h1>Company Settings</h1><div class="settings-tabs"><section id="company"><input name="company" value="Keep company settings"></section></div></main>'''
def main():
 server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(ROOT/'connectors')))
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for platform in ['desktop','android']:
   page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.add_init_script('window.opens=0;'+('window.backwoodsUpdates={open:async()=>window.opens++};' if platform=='desktop' else "window.Capacitor={isPluginAvailable:n=>n==='BackwoodsUpdater',nativePromise:async(n,m)=>{if(n!=='BackwoodsUpdater'||m!=='open')throw Error('Wrong plugin');window.opens++;}};"))
   page.goto(f'http://127.0.0.1:{server.server_port}/')
   page.evaluate("document.body.innerHTML='<main><h1>Sign in</h1></main>'")
   page.add_script_tag(url=f'http://127.0.0.1:{server.server_port}/updater-entry.js')
   page.wait_for_timeout(100)
   assert page.locator('#backwoods-app-updates').count()==0
   assert page.locator('#backwoods-settings-updates').count()==0
   page.evaluate('(html)=>document.body.innerHTML=html',MAIN)
   page.get_by_role('button',name='Open app updates',exact=True).wait_for()
   assert not page.locator('#legacy-controls').is_visible()
   assert page.locator('#backwoods-settings-updates').evaluate("e=>e.parentElement.id")=='settings-card'
   page.get_by_role('button',name='Open app updates',exact=True).click();assert page.evaluate('opens')==1
   page.evaluate("document.body.innerHTML='<main><h1>Orders</h1></main>'")
   page.wait_for_timeout(100);assert page.locator('#backwoods-settings-updates').count()==0
   page.evaluate('(html)=>document.body.innerHTML=html',VENDOR)
   page.get_by_role('button',name='Open app updates',exact=True).wait_for()
   assert page.locator('[name=company]').input_value()=='Keep company settings'
   assert page.locator('#backwoods-settings-updates').evaluate("e=>e.parentElement.className")=='settings-tabs'
   page.get_by_role('button',name='Open app updates',exact=True).click();assert page.evaluate('opens')==2
   assert page.locator('#backwoods-app-updates').count()==0
   assert not errors,errors
   page.close()
  browser.close()
 server.shutdown();server.server_close();thread.join()
 print('PASS: Main/Vendor controls appear only in Settings on desktop and Android bridges, disappear on navigation, preserve company fields, and open the correct native updater; no floating buttons or page errors.')
if __name__=='__main__':main()
