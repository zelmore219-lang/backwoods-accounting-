"""Publish an Accounting-only update while retaining every other app artifact."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request
from build_update_release import ROOT,REPO,sha
from publish_updates import FEED,release,create_release,by_id,upload,verify_assets,gh

def read_feed():
    with urllib.request.urlopen(urllib.request.Request(FEED,headers={'Cache-Control':'no-cache'}),timeout=60) as response:return json.load(response)

def revised_feed(previous,windows,android,commit):
    updated=copy.deepcopy(previous)
    for platform,new in [('windows',windows),('android',android)]:
        old=previous['apps']['accounting'][platform]
        if tuple(map(int,new['version'].split('.')))<=tuple(map(int,old['version'].split('.'))):raise ValueError('Accounting versions must increase')
        if platform=='android' and (new['packageName']!=old['packageName'] or new['certificateSha256']!=old['certificateSha256']):raise ValueError('Do not change the installed Accounting signing identity')
        updated['apps']['accounting'][platform]=new
    updated['sourceCommit']=commit
    updated['apps']['accounting']['notes']='Android uses a non-debuggable release build with the retained signing identity. Windows installer checks that the app has exited before replacing files. Company data is preserved. Play Protect reputation on a physical device is not established by emulator tests.'
    updated.pop('reusedAccounting',None)
    return updated

def prepare(tag,directory):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}',tag) or tag=='app-updates':raise ValueError('Use a new versioned release tag')
    previous=read_feed()
    version=json.loads((ROOT/'desktop/package.json').read_text())['version']
    windows=ROOT/f'dist/windows/Backwoods-Business-Accounting-Setup-{version}.exe'
    apk=ROOT/'android-apps/accounting/android/app/build/outputs/apk/release/app-release.apk'
    tools=Path(os.environ['ANDROID_HOME'])/'build-tools/35.0.0'
    certificate=subprocess.check_output([str(tools/'apksigner'),'verify','--print-certs',str(apk)],text=True)
    digest=re.search(r'Signer #1 certificate SHA-256 digest: ([a-f0-9]{64})',certificate)[1]
    if digest!=(ROOT/'android-apps/update-signing-certificate.txt').read_text().strip():raise ValueError('Unexpected APK signing identity')
    badging=subprocess.check_output([str(tools/'aapt'),'dump','badging',str(apk)],text=True)
    package=re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",badging)
    if not package or package[1]!='com.backwoodsbrew.accounting' or package[3]!=version:raise ValueError('APK identity/version mismatch')
    manifest=subprocess.check_output([str(tools/'aapt'),'dump','xmltree',str(apk),'AndroidManifest.xml'],text=True)
    if re.search(r'android:debuggable[^\n]*0xffffffff',manifest) or 'com.backwoodsbrew.updates.UpdateFileProvider' not in manifest:raise ValueError('Not the corrected non-debuggable release APK')
    if windows.read_bytes()[:2]!=b'MZ':raise ValueError('Invalid Windows installer')
    directory.mkdir(parents=True,exist_ok=True)
    paths=[directory/windows.name,directory/f'Backwoods-Business-Accounting-{version}-release.apk']
    for source,destination in zip([windows,apk],paths):shutil.copy2(source,destination)
    def artifact(path):return {'version':version,'url':f'https://github.com/{REPO}/releases/download/{tag}/{path.name}','size':path.stat().st_size,'sha256':sha(path)}
    android={**artifact(paths[1]),'packageName':package[1],'versionCode':int(package[2]),'certificateSha256':digest,'minSdk':int(re.search(r"sdkVersion:'(\d+)'",badging)[1]),'abis':re.findall(r"'([^']+)'",re.search(r'native-code: (.+)',badging)[1])}
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    feed=revised_feed(previous,artifact(paths[0]),android,commit)
    (directory/'backwoods-updates.json').write_text(json.dumps(feed,indent=2)+'\n')
    (directory/'base-feed.json').write_text(json.dumps(previous,indent=2)+'\n')
    (directory/'SHA256SUMS.txt').write_text('\n'.join(sha(p)+'  '+p.name for p in paths)+'\n')
    (directory/'RELEASE_NOTES.md').write_text('''Accounting 1.0.7 — Windows and Android

Android is a non-debuggable release build signed with the existing Accounting key. Android 17 upgrade and private-data preservation tests are run separately; those checks do not clear a Google Play Protect warning on a phone. Keep any working installation and its records. Do not disable Play Protect.

Windows detects a locked Accounting executable before replacing program files. Save work, use File → Quit or Exit from the tray, then click Retry. Closing the window can leave the tray process running.

Main and Vendor packages and feed entries are retained unchanged.
''')
    return feed,previous,paths

def publish(tag,directory,feed,previous,paths):
    if read_feed()!=previous:raise ValueError('Update feed changed; prepare again before publishing')
    files=[*paths,directory/'backwoods-updates.json',directory/'SHA256SUMS.txt']
    current=release(tag)
    if current is None:current=create_release(tag,feed['sourceCommit'],'Accounting 1.0.7 — Windows and Android',(directory/'RELEASE_NOTES.md').read_text())
    for path in files:upload(current,path)
    verify_assets(by_id(current['id']),files)
    if read_feed()!=previous:raise ValueError('Update feed changed during upload; channel not modified')
    gh('release','edit',tag,'--draft=false','--prerelease','--latest=false')
    channel=release('app-updates')
    if not channel:raise ValueError('Existing update channel is missing')
    upload(channel,directory/'backwoods-updates.json',replace=True)
    verify_assets(by_id(channel['id']),[directory/'backwoods-updates.json'])
    print(f'https://github.com/{REPO}/releases/tag/{tag}')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--tag',required=True);parser.add_argument('--out',type=Path,default=ROOT/'dist/accounting-update');parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    feed,previous,paths=prepare(args.tag,args.out)
    if args.publish:publish(args.tag,args.out,feed,previous,paths)
    else:print('Prepared Accounting-only update; channel unchanged.')
