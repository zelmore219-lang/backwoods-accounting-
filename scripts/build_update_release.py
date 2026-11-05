"""Collect verified packages and generate the feed consumed by all three apps."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
REPO='zelmore219-lang/backwoods-accounting-'
APPS={
    'accounting':('Backwoods Business Accounting','Backwoods-Business-Accounting','com.backwoodsbrew.accounting'),
    'vendor':('Backwoods Vendor Connected','Backwoods-Vendor-Ordering-Connected','com.backwoodsbrew.vendor.connected'),
    'main':('Backwoods Brew Connected','Backwoods-Brew-Connected','com.backwoodsbrew.main.connected'),
}

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        while block:=f.read(1024*1024):digest.update(block)
    return digest.hexdigest()

def retained_accounting():
    url=f'https://github.com/{REPO}/releases/download/app-updates/backwoods-updates.json'
    with urllib.request.urlopen(url,timeout=60) as response:current=json.load(response)
    entry=current['apps']['accounting'];folder=ROOT/'.build-resources/reused-accounting';folder.mkdir(parents=True,exist_ok=True)
    result={}
    for platform in ['windows','android']:
        artifact=entry[platform]
        if not artifact['url'].startswith(f'https://github.com/{REPO}/releases/download/') or not re.fullmatch('[a-f0-9]{64}',artifact['sha256']):raise ValueError('Untrusted retained Accounting artifact')
        destination=folder/Path(artifact['url']).name
        if not destination.exists() or sha(destination)!=artifact['sha256']:
            with urllib.request.urlopen(artifact['url'],timeout=120) as response,destination.open('wb') as output:
                count=0
                while block:=response.read(1024*1024):
                    count+=len(block)
                    if count>artifact['size'] or count>1024**3:raise ValueError('Retained Accounting artifact exceeds expected size')
                    output.write(block)
        if destination.stat().st_size!=artifact['size'] or sha(destination)!=artifact['sha256']:raise ValueError('Retained Accounting artifact did not verify')
        result[platform]=destination
    return entry,result

def build(tag,out,reuse_accounting=False):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}',tag) or tag=='app-updates':raise ValueError('Choose a versioned package release tag, not app-updates')
    out.mkdir(parents=True,exist_ok=True)
    sdk=Path(os.environ['ANDROID_HOME'])/'build-tools/35.0.0'
    signer=sdk/('apksigner.bat' if os.name=='nt' else 'apksigner');aapt=sdk/('aapt.exe' if os.name=='nt' else 'aapt')
    expected=(ROOT/'android-apps/update-signing-certificate.txt').read_text().strip()
    feed={'schemaVersion':1,'sourceCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'apps':{}}
    checks=[]
    retained=retained_accounting() if reuse_accounting else None
    for kind,(name,prefix,package) in APPS.items():
        project=ROOT/'desktop' if kind=='accounting' else ROOT/'source-app-updates'/kind
        version=json.loads((project/'package.json').read_text())['version']
        win=ROOT/'dist/windows' if kind=='accounting' else ROOT/'dist/source-app-updates'/kind
        source=win/f'{prefix}-Setup-{version}.exe'
        apk=ROOT/'android-apps'/kind/'android/app/build/outputs/apk/debug/app-debug.apk'
        if kind=='accounting' and retained:
            if any(retained[0][platform]['version']!=version for platform in ['windows','android']):raise ValueError('Keep the existing Accounting version when reusing its packages')
            source=retained[1]['windows'];apk=retained[1]['android']
        cert=subprocess.check_output([str(signer),'verify','--print-certs',str(apk)],text=True,stderr=subprocess.STDOUT)
        certificate=re.search(r'Signer #1 certificate SHA-256 digest: ([a-f0-9]{64})',cert).group(1)
        if certificate!=expected:raise ValueError(f'{kind}: Android signing key changed; refusing to publish an incompatible update')
        badging=subprocess.check_output([str(aapt),'dump','badging',str(apk)],text=True)
        identity=re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",badging)
        if not identity or identity[1]!=package or identity[3]!=version:raise ValueError(f'{kind}: packaged app identity/version mismatch')
        min_sdk=int(re.search(r"sdkVersion:'(\d+)'",badging)[1])
        native=re.search(r'native-code: (.+)',badging)
        abis=re.findall(r"'([^']+)'",native[1]) if native else ['arm64-v8a','armeabi-v7a','x86','x86_64']
        if source.read_bytes()[:2]!=b'MZ':raise ValueError('Not a Windows installer')
        win_out=out/source.name;shutil.copy2(source,win_out)
        apk_name=('Backwoods-Vendor-Connected' if kind=='vendor' else prefix)+f'-{version}-test.apk'
        apk_out=out/apk_name;shutil.copy2(apk,apk_out)
        def artifact(p):
            digest=sha(p);checks.append(digest+'  '+p.name);return {'version':version,'url':f'https://github.com/{REPO}/releases/download/{tag}/{p.name}','sha256':digest,'size':p.stat().st_size}
        feed['apps'][kind]={'name':name,'notes':('App updates now opens only from Settings; no floating update button. Windows Main includes a safe one-time chooser when more than one previous profile is found.' if kind=='main' else 'App updates now opens only from Settings; no floating update button.' if kind=='vendor' else 'Accounting packages are unchanged in this Main/Vendor-only update.' if retained else 'Native update wizard for Windows and Android. Checksums and Android signing identities are verified before installation. Your records stay in the installed app.'),'windows':artifact(win_out),'android':{**artifact(apk_out),'packageName':package,'versionCode':int(identity[2]),'minSdk':min_sdk,'abis':abis,'certificateSha256':certificate}}
    feed['reusedAccounting']=reuse_accounting
    (out/'backwoods-updates.json').write_text(json.dumps(feed,indent=2)+'\n')
    (out/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n')
    (out/'RELEASE_NOTES.md').write_text('''# Backwoods app updates — Windows and Android

All three apps now include App updates: current/latest versions, checks, verified downloads and user-approved installation. Updates are checked on startup and every six hours while Windows apps run; Android checks on startup at most once every six hours. Auto-download is optional. Windows uses a setup wizard; Android requires system installation approval.

**Windows:** install this version manually once to fix GitHub download redirects. Later versions can then be installed through App updates.

**Android:** Main 8.2.5 and Vendor 4.1.6 can download this update through their existing App updates button. Choose Check, Download, then Install and approve Android's installation prompt. In the new Main and Vendor versions, App updates is available only in Settings and the floating button is removed. Accounting keeps its existing update entry. Back up records before updating. Never uninstall an existing app to fix a signing conflict.

Android updates are signed with the retained test key used by Accounting 1.0.3 and Vendor 4.1.5. Earlier APKs signed with a different key cannot be upgraded in place, including the older Main APK. Those installations require their original signing key. Windows installers remain unsigned. Windows installation, Android installation and physical-device operation require device testing.

Future releases are built by the App updates GitHub Actions workflow. The public app-updates release hosts the shared feed; this versioned release contains immutable package downloads. No GitHub token is embedded in any app.
''')
    print('Verified and prepared six packages plus the shared updater feed in '+str(out))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--tag',required=True);parser.add_argument('--reuse-accounting',action='store_true');parser.add_argument('--out',type=Path,default=ROOT/'dist/update-release');args=parser.parse_args();build(args.tag,args.out,args.reuse_accounting)
