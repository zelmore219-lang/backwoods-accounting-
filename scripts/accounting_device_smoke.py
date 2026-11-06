"""Exercise real Android package upgrades; never runs against a user's phone."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dist/accounting-device-check'
PACKAGE='com.backwoodsbrew.accounting'
BASE='https://github.com/zelmore219-lang/backwoods-accounting-/releases/download/'

def adb(*args,check=True):
    result=subprocess.run(['adb',*args],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
    if check and result.returncode:raise RuntimeError(result.stdout)
    return result.stdout.strip()

def download(tag):
    with urllib.request.urlopen(BASE+tag+'/backwoods-updates.json',timeout=60) as response:feed=json.load(response)
    artifact=feed['apps']['accounting']['android']
    if not artifact['url'].startswith(BASE+tag+'/'):raise ValueError('Unexpected package source')
    path=OUT/('accounting-'+artifact['version']+'.apk')
    with urllib.request.urlopen(artifact['url'],timeout=90) as response,path.open('wb') as output:
        while block:=response.read(1024*1024):output.write(block)
    assert path.stat().st_size==artifact['size']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==artifact['sha256']
    return path,artifact['version']

def hierarchy():
    adb('shell','uiautomator','dump','/sdcard/accounting-test.xml',check=False)
    return adb('shell','cat','/sdcard/accounting-test.xml',check=False)

def wait_text(value,seconds=40):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        text=hierarchy()
        if value in text:return text
        time.sleep(1)
    raise AssertionError('Android UI did not show: '+value+'\n'+text)

def click_text(value):
    for _ in range(4):
        xml=hierarchy()
        if '<hierarchy' in xml:
            for node in ET.fromstring(xml).iter('node'):
                if node.get('text')==value:
                    x1,y1,x2,y2=map(int,re.findall(r'\d+',node.get('bounds')))
                    if x2>x1 and y2>y1:
                        adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2));return
        width,height=map(int,re.findall(r'(\d+)x(\d+)',adb('shell','wm','size'))[-1])
        adb('shell','input','swipe',str(width//2),str(height*8//10),str(width//2),str(height*3//10),'350')
    raise AssertionError('Android button was not accessible: '+value)

def launch_and_check(label,engine=False):
    adb('shell','am','force-stop',PACKAGE)
    adb('logcat','-c')
    result=adb('shell','am','start','-W','-n',PACKAGE+'/.MainActivity')
    assert 'Error' not in result,result
    xml=wait_text('Sign in to your company')
    if engine:
        click_text("Open this device's saved books")
        # A fresh emulator has no company account. This error is returned only
        # after Python, SQLite and the local accounting engine have started.
        xml=wait_text('Sign in to Firebase and create the company owner account first.',60)
    (OUT/(label+'-ui.xml')).write_text(xml)
    log=adb('logcat','-d')
    (OUT/(label+'-logcat.txt')).write_text(log)
    assert 'FATAL EXCEPTION' not in log,log[-12000:]
    assert adb('shell','pidof',PACKAGE),'Accounting process exited'

def install(path,replace=False):
    result=adb('install',*(['-r'] if replace else []),str(path))
    print(result,flush=True)
    assert 'Success' in result,result

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    # Google APIs emulator images support root for test data inspection. No
    # verifier, Play Protect or Android installation policy is disabled here.
    adb('root');adb('wait-for-device')
    print('Android:',adb('shell','getprop','ro.build.version.release'),'API:',adb('shell','getprop','ro.build.version.sdk'),'page size:',adb('shell','getconf','PAGE_SIZE'),flush=True)
    assert not adb('shell','pm','path',PACKAGE,check=False),'Use a fresh disposable emulator'
    old,_=download('app-updaters-2026-11-05')
    published,_=download('android-install-fix-2026-11-05')
    install(old);launch_and_check('old')
    sentinel='/data/user/0/'+PACKAGE+'/files/upgrade-preserved.txt'
    adb('shell','run-as',PACKAGE,'sh','-c',"'echo retained-company-data > files/upgrade-preserved.txt'")
    install(published,replace=True);launch_and_check('published')
    assert adb('shell','cat',sentinel)=='retained-company-data'
    candidate=ROOT/'android-apps/accounting/android/app/build/outputs/apk/release/app-release.apk'
    install(candidate,replace=True)
    assert adb('shell','cat',sentinel)=='retained-company-data'
    launch_and_check('release',engine=True)
    package=adb('shell','dumpsys','package',PACKAGE)
    (OUT/'release-package.txt').write_text(package)
    assert 'versionName=1.0.7' in package
    flags=re.search(r'^\s*flags=\[([^\]]*)\]',package,re.M)
    assert flags and 'DEBUGGABLE' not in flags[1],flags
    (OUT/'result.txt').write_text('PASS: Android 17 installed 1.0.4, upgraded to published 1.0.6, then to retained-key non-debuggable 1.0.7; private data survived both upgrades and the native accounting engine ran. This Google APIs image does not validate Play Protect reputation on a physical phone.\n')
    print((OUT/'result.txt').read_text(),flush=True)

if __name__=='__main__':
    try:main()
    except Exception:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'failure-logcat.txt').write_text(adb('logcat','-d',check=False))
        (OUT/'failure-package.txt').write_text(adb('shell','dumpsys','package',PACKAGE,check=False))
        raise
