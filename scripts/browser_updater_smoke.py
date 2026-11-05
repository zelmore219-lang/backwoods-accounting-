"""Exercise the actual update wizard UI with a deterministic native bridge fixture."""
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
import threading
import shutil
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
BRIDGE=r'''
window.fixtureCalls=[];
let listener=()=>{};
let state={phase:'idle',message:'Ready to check for updates.',currentVersion:'1.0.4',latestVersion:'',percent:0,enabled:true,autoDownload:false,feedUrl:'https://github.com/zelmore219-lang/backwoods-accounting-/releases/download/app-updates/backwoods-updates.json'};
window.updates={onState:callback=>listener=callback,action:async(name,value)=>{
 window.fixtureCalls.push({name,value});
 if(name==='configure')state={...state,...value,phase:'idle',message:'Update settings saved.'};
 if(name==='check')state={...state,phase:'available',latestVersion:'1.0.5',message:'A new version is available.',notes:'<img src=x onerror=alert(1)> must be plain text'};
 if(name==='download'){state={...state,phase:'downloading',percent:50,message:'Downloading and verifying…'};listener(state);await new Promise(r=>setTimeout(r,100));state={...state,phase:'downloaded',percent:100,message:'Update verified. Save your work and choose Install when ready.'};}
 if(name==='install')state={...state,phase:'installing',message:'Opening Windows setup…'};
 return state;
}};
'''
def main():
    output=ROOT/'dist/updater/screenshots';output.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(ROOT/'connectors/updater')))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=shutil.which('chromium') or None,headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':760,'height':800});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.add_init_script(BRIDGE);page.goto(f'http://127.0.0.1:{server.server_port}/wizard.html')
        page.locator('#current').get_by_text('1.0.4',exact=True).wait_for()
        assert page.locator('#download').is_disabled() and page.locator('#install').is_disabled()
        page.locator('#auto').check();page.locator('#save').click();page.get_by_text('Update settings saved.',exact=True).wait_for()
        assert page.evaluate('fixtureCalls.find(c=>c.name==="configure").value.autoDownload') is True
        page.locator('#check').click();page.locator('#latest').get_by_text('1.0.5',exact=True).wait_for()
        assert page.locator('img').count()==0
        page.locator('#download').click();page.get_by_text('Update verified. Save your work and choose Install when ready.',exact=True).wait_for()
        assert page.locator('#install').is_enabled()
        page.screenshot(path=str(output/'verified-update.png'),full_page=True)
        page.locator('#install').click();page.get_by_text('Opening Windows setup…',exact=True).wait_for()
        assert page.evaluate('fixtureCalls.filter(c=>c.name==="install").length')==1
        assert not errors,errors
        browser.close()
    server.shutdown();server.server_close();thread.join()
    print('PASS: actual wizard renders versions, saves settings, checks, downloads, gates installation and displays feed notes as plain text; no page errors. Native IPC/integrity is verified separately by updater-electron.test.cjs.')
if __name__=='__main__':main()
