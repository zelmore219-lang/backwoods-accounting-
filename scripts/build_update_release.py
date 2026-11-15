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

def retained_app(kind):
    url=f'https://github.com/{REPO}/releases/download/app-updates/backwoods-updates.json'
    with urllib.request.urlopen(url,timeout=60) as response:current=json.load(response)
    entry=current['apps'][kind];folder=ROOT/('.build-resources/reused-'+kind);folder.mkdir(parents=True,exist_ok=True)
    if kind in {'main','vendor'}:
        previous=current['sourceCommit']
        if not re.fullmatch('[a-f0-9]{40}',previous):raise ValueError('Retained source provenance is missing')
        if subprocess.run(['git','cat-file','-e',previous+'^{commit}'],cwd=ROOT,capture_output=True).returncode:
            subprocess.run(['git','fetch','--no-tags','--depth=1','origin',previous],cwd=ROOT,check=True)
        paths=['source-app-updates/'+kind,'android-apps/'+kind,'android-apps/shared-updater','connectors','scripts/build_source_installers.py','scripts/prepare_updaters.py','scripts/prepare_app_icons.py']
        subprocess.run(['git','diff','--exit-code',previous,'HEAD','--',*paths],cwd=ROOT,check=True)
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

def retained_accounting():return retained_app('accounting')

def build(tag,out,reuse_accounting=False,reuse_source_apps=False):
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
        selected=retained if kind=='accounting' else retained_app(kind) if reuse_source_apps else None
        if selected:
            if any(selected[0][platform]['version']!=version for platform in ['windows','android']):raise ValueError('Keep the existing '+kind+' version when reusing its packages')
            source=selected[1]['windows'];apk=selected[1]['android']
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
        feed['apps'][kind]={'name':name,'notes':('Removed Subscription, Walkthrough and Launch Wizard navigation while retaining business records and sign-in.' if kind=='main' else 'Clock In / Clock Out uses the existing Employee UID, Wholesale job, server timestamps and review workflow; keep Employee Owner service running.' if kind=='vendor' else 'Payroll Management: approved Employee hours, manual gross pay, owner review, CSV/Excel, HR.my or verified external provider workflow, actual reports and bank reconciliation. No payroll is submitted or paid by downloading an export.'),'windows':artifact(win_out),'android':{**artifact(apk_out),'packageName':package,'versionCode':int(identity[2]),'minSdk':min_sdk,'abis':abis,'certificateSha256':certificate}}
    feed['reusedAccounting']=reuse_accounting
    feed['reusedSourceApps']=reuse_source_apps
    (out/'backwoods-updates.json').write_text(json.dumps(feed,indent=2)+'\n')
    (out/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n')
    (out/'RELEASE_NOTES.md').write_text((ROOT/'docs/COORDINATED-OWNER-GUIDE.md').read_text()+'\nWindows installers are unsigned. Android uses the retained compatible signing certificate; install over the existing package without uninstalling. No physical-device or live provider acceptance is claimed.\n')
    print('Verified and prepared six packages plus the shared updater feed in '+str(out))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--tag',required=True);parser.add_argument('--reuse-accounting',action='store_true');parser.add_argument('--reuse-source-apps',action='store_true');parser.add_argument('--out',type=Path,default=ROOT/'dist/update-release');args=parser.parse_args();build(args.tag,args.out,args.reuse_accounting,args.reuse_source_apps)
