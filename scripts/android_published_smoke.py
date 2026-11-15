"""Exercise the exact public APK on a disposable Android emulator only."""
import hashlib,json,re,shutil,subprocess,sys,time,urllib.request,xml.etree.ElementTree as ET
from pathlib import Path

APP=sys.argv[1]
assert APP in {'main','vendor','accounting','employees','driver'}
FEEDS={
 'employees':'https://github.com/zelmore219-lang/backwoods-brew-releases/releases/download/employee-updates/backwoods-employees-updates.json',
 'driver':'https://github.com/zelmore219-lang/backwoods-brew-releases/releases/download/driver-updates/backwoods-driver-updates.json',
}
URL=FEEDS.get(APP,'https://github.com/zelmore219-lang/backwoods-accounting-/releases/download/app-updates/backwoods-updates.json')
ROOT=Path('test-results/android-published')/APP;ROOT.mkdir(parents=True,exist_ok=True)

def adb(*args,check=True):
 return subprocess.run(['adb',*args],capture_output=True,text=True,check=check,timeout=120).stdout

def snapshot(stage):
 adb('shell','uiautomator','dump','/sdcard/backwoods-audit.xml')
 xml=adb('shell','cat','/sdcard/backwoods-audit.xml')
 (ROOT/(stage+'.xml')).write_text(xml)
 with (ROOT/(stage+'.png')).open('wb') as out:subprocess.run(['adb','exec-out','screencap','-p'],stdout=out,check=True,timeout=30)
 tree=ET.fromstring(xml[xml.index('<?xml'):])
 return ' '.join(n.attrib.get('text','')+' '+n.attrib.get('content-desc','') for n in tree.iter('node')).casefold()

def open_app(stage):
 adb('shell','am','force-stop',PACKAGE)
 adb('logcat','-c')
 adb('shell','monkey','-p',PACKAGE,'-c','android.intent.category.LAUNCHER','1')
 last=''
 for attempt in range(18):
  time.sleep(2)
  last=snapshot(stage)
  xml=(ROOT/(stage+'.xml')).read_text()
  nodes=list(ET.fromstring(xml[xml.index('<?xml'):]).iter('node'))
  inputs=[node for node in nodes if node.attrib.get('class')=='android.widget.EditText']
  # WebView exposes password inputs structurally without exposing their hint as
  # text on every version. Require the real editable fields and masked input.
  password=any(node.attrib.get('password')=='true' for node in inputs)
  if (('password' in last or password) and ('sign in' in last or 'login' in last or 'username' in last) and len(inputs)>=2):break
  # Dismiss OS permission prompts on the disposable device, not application data.
  for label in ['While using the app','Allow','Don’t allow','Don\'t allow']:
   xml=(ROOT/(stage+'.xml')).read_text()
   for node in ET.fromstring(xml[xml.index('<?xml'):]).iter('node'):
    if node.attrib.get('text')==label:
     b=list(map(int,re.findall(r'\d+',node.attrib.get('bounds',''))))
     if len(b)==4:adb('shell','input','tap',str((b[0]+b[2])//2),str((b[1]+b[3])//2))
 else:raise AssertionError('No usable sign-in screen: '+last[:1000])
 foreground=adb('shell','dumpsys','activity','activities')
 assert PACKAGE in foreground,'The installed app is not running'
 logs=adb('logcat','-d','-s','AndroidRuntime:E')
 (ROOT/(stage+'-crashes.log')).write_text(logs)
 assert not ('FATAL EXCEPTION' in logs and PACKAGE in logs),logs
 assert 'application error' not in last and 'keeps stopping' not in last,last
 return last

with urllib.request.urlopen(URL,timeout=60) as response:feed=json.load(response)
INFO=feed['apps'][APP]['android'];PACKAGE=INFO['packageName']
assert re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_.]+',PACKAGE)
artifact=ROOT/'published.apk';digest=hashlib.sha256();count=0
with urllib.request.urlopen(INFO['url'],timeout=120) as response,artifact.open('wb') as out:
 while chunk:=response.read(1024*1024):
  count+=len(chunk);assert count<=INFO['size'];digest.update(chunk);out.write(chunk)
assert count==INFO['size'] and digest.hexdigest()==INFO['sha256']
sdk=Path(__import__('os').environ['ANDROID_HOME'])/'build-tools/35.0.0'
cert=subprocess.check_output([str(sdk/'apksigner'),'verify','--print-certs',str(artifact)],text=True)
fingerprint=re.search(r'Signer #1 certificate SHA-256 digest: ([a-f0-9]{64})',cert)[1]
assert fingerprint==INFO['certificateSha256']
badging=subprocess.check_output([str(sdk/'aapt'),'dump','badging',str(artifact)],text=True)
assert f"name='{PACKAGE}'" in badging and f"versionName='{INFO['version']}'" in badging
assert f"versionCode='{INFO['versionCode']}'" in badging
subprocess.run(['adb','install','-r',str(artifact)],check=True,timeout=120)
open_app('installed')
canary=adb('shell','run-as',PACKAGE,'mkdir','-p','files',check=False)
private_read=subprocess.run(['adb','shell','run-as',PACKAGE,'tee','files/backwoods-audit-canary'],input='disposable-record-preservation',capture_output=True,text=True,timeout=20)
has_canary=private_read.returncode==0
adb('shell','settings','put','system','accelerometer_rotation','0')
adb('shell','settings','put','system','user_rotation','1');time.sleep(2);snapshot('landscape')
adb('shell','settings','put','system','user_rotation','0')
subprocess.run(['adb','install','-r',str(artifact)],check=True,timeout=120)
open_app('reinstalled')
if has_canary:assert adb('shell','run-as',PACKAGE,'cat','files/backwoods-audit-canary').strip()=='disposable-record-preservation'
result={'app':APP,'version':INFO['version'],'packageName':PACKAGE,'sha256':digest.hexdigest(),'certificateSha256':fingerprint,'publicBytesVerified':True,'installed':True,'signInRendered':True,'reinstalled':True,'privateCanaryPreserved':True if has_canary else 'release sandbox: not accessible','nativeCrash':False,'physicalDevice':False,'authenticatedWorkflow':'verified separately with isolated source/emulator suites; not implied by launch test'}
(ROOT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
artifact.unlink()
print('ANDROID_PUBLISHED_ACCEPTANCE '+json.dumps(result),flush=True)
