"""Publish an already-tested Main build; preserve every other updater entry."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
from build_update_release import REPO, sha
from publish_updates import FEED, by_id, create_release, gh, release, upload, verify_assets

VERSION='8.2.9'
SOURCE='eaed598a242a16a2b775ef009cbc0598177fefe5'
RUN=42913704687
TAG='main-receipt-repairs-8.2.9'
NAMES={'windows':'Backwoods-Brew-Connected-Setup-8.2.9.exe','android':'Backwoods-Brew-Connected-8.2.9.apk'}

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))
def version(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+',value):raise ValueError('Invalid updater version')
    return tuple(map(int,value.split('.')))

def prepare(previous,artifacts,android):
    if previous.get('schemaVersion')!=1 or not {'main','vendor','accounting'}.issubset(previous.get('apps',{})):
        raise ValueError('The existing shared update feed is incomplete')
    result=copy.deepcopy(previous)
    for platform,artifact in artifacts.items():
        old=previous['apps']['main'][platform]
        if version(old['version'])>version(VERSION):raise ValueError('A newer Main update is already published')
        if old['version']==VERSION and old['sha256']!=artifact['sha256']:
            raise ValueError('Changed packages require a new version; refusing to replace an existing Main build')
        result['apps']['main'][platform]={**old,**artifact}
    result['apps']['main']['android'].update(android)
    result['apps']['main']['notes']='Main 8.2.9: removes the embedded Central Accounting and Wholesale Management launchers; fixes complete receipts, in-app print previews, native printing and receipt reprints without pop-ups. Saved transactions, inventory and accounting integration are preserved.'
    result['sourceCommit']=SOURCE
    result['updatedApps']=['main']
    for name,entry in previous['apps'].items():
        if name!='main' and result['apps'][name]!=entry:raise ValueError('Another application update entry changed')
    return result

def read_public(suffix=''):
    request=urllib.request.Request(FEED+suffix,headers={'Cache-Control':'no-cache','User-Agent':'Backwoods-Main-Update-Publisher'})
    with urllib.request.urlopen(request,timeout=45) as response:raw=response.read(1024*1024+1)
    if len(raw)>1024*1024:raise ValueError('Update feed exceeds its supported size')
    return raw,json.loads(raw)

def feed_asset(channel):
    return next(a for a in channel['assets'] if a['name']=='backwoods-updates.json')

def same_asset(first,second):
    return first['id']==second['id'] and first['digest']==second['digest']

def verify_public_package(info):
    request=urllib.request.Request(info['url'],headers={'Cache-Control':'no-cache'})
    digest=hashlib.sha256();size=0
    with urllib.request.urlopen(request,timeout=120) as response:
        while block:=response.read(1024*1024):
            size+=len(block)
            if size>info['size']:raise ValueError('Public package exceeds declared size')
            digest.update(block)
    if size!=info['size'] or digest.hexdigest()!=info['sha256']:raise ValueError('Public package failed download verification')

def publish(directory):
    run=json.loads(subprocess.check_output(['gh','api',f'repos/{REPO}/actions/runs/{RUN}'],text=True))
    if run['conclusion']!='success' or run['head_sha']!=SOURCE or run['name']!='Main app receipt repair packages':
        raise ValueError('Publication requires the specific successful Main repair build')
    channel=release('app-updates')
    if not channel or channel['draft']:raise ValueError('The existing public update channel must already exist')
    original_asset=feed_asset(channel)
    raw,previous=read_public('?check='+str(time.time_ns()))
    if original_asset['digest']!='sha256:'+hashlib.sha256(raw).hexdigest():
        raise ValueError('The public feed and release asset disagree; retry after the current publication finishes')
    output=directory/'publication';output.mkdir(parents=True,exist_ok=True)
    (output/'previous-feed.json').write_bytes(raw)
    expected={Path(name).name:digest for digest,name in (line.split(maxsplit=1) for line in (directory/'SHA256SUMS.txt').read_text().splitlines())}
    paths={platform:directory/name for platform,name in NAMES.items()}
    for path in paths.values():
        if sha(path)!=expected.get(path.name):raise ValueError('Tested workflow package checksum mismatch: '+path.name)
    if paths['windows'].open('rb').read(2)!=b'MZ':raise ValueError('The Main Windows package is not an installer')
    sdk=Path(os.environ['ANDROID_HOME'])/'build-tools/35.0.0'
    cert=subprocess.check_output([str(sdk/'apksigner'),'verify','--print-certs',str(paths['android'])],text=True,stderr=subprocess.STDOUT)
    certificate=re.search(r'Signer #1 certificate SHA-256 digest: ([a-f0-9]{64})',cert)[1]
    retained=(Path(__file__).resolve().parents[1]/'android-apps/update-signing-certificate.txt').read_text().strip()
    if certificate!=retained:raise ValueError('Main Android signing identity changed')
    badging=subprocess.check_output([str(sdk/'aapt'),'dump','badging',str(paths['android'])],text=True)
    identity=re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'",badging)
    if not identity or (identity[1],identity[2],identity[3])!=('com.backwoodsbrew.main.connected','80209',VERSION):
        raise ValueError('Main Android package identity/version mismatch')
    native=re.search(r'native-code: (.+)',badging)
    android={'packageName':identity[1],'versionCode':int(identity[2]),'minSdk':int(re.search(r"sdkVersion:'(\d+)'",badging)[1]),
             'abis':re.findall(r"'([^']+)'",native[1]) if native else ['arm64-v8a','armeabi-v7a','x86','x86_64'],
             'certificateSha256':certificate}
    artifacts={platform:{'version':VERSION,'url':f'https://github.com/{REPO}/releases/download/{TAG}/{path.name}',
                         'sha256':sha(path),'size':path.stat().st_size} for platform,path in paths.items()}
    feed=prepare(previous,artifacts,android)
    payload=(output/'backwoods-updates.json');payload.write_text(json.dumps(feed,indent=2)+'\n')
    notes='Main-only receipt repairs. Windows and Android packages come from the successful tested Main 8.2.9 build. Accounting and Vendor update entries are unchanged. Use Main Settings → App updates → Check → Download → Install. Back up records and close Main before updating. Physical printer/device and live Firebase checks remain for the target devices.'
    current=release(TAG) or create_release(TAG,SOURCE,'Backwoods Main 8.2.9 — receipt repairs',notes)
    for path in paths.values():
        exists=any(a['name']==path.name for a in by_id(current['id'])['assets'])
        if not exists and not current['draft']:raise ValueError('Published Main release is missing a package; use a new tag')
        upload(current,path)
    verify_assets(by_id(current['id']),list(paths.values()))
    gh('release','edit',TAG,'--draft=false','--prerelease','--latest=false')
    for artifact in artifacts.values():verify_public_package(artifact)
    fresh=feed_asset(by_id(channel['id']))
    if not same_asset(original_asset,fresh):raise ValueError('The update channel changed while packages uploaded; refusing to overwrite it')
    try:upload(channel,payload,replace=True)
    except Exception:
        latest=by_id(channel['id']);asset=next((a for a in latest['assets'] if a['name']==payload.name),None)
        if asset and asset.get('digest')=='sha256:'+sha(payload):pass
        elif not asset:
            rollback=output/'rollback'/payload.name;rollback.parent.mkdir();rollback.write_bytes(raw)
            upload(channel,rollback);raise
        else:raise
    verify_assets(by_id(channel['id']),[payload])
    for attempt in range(8):
        try:
            _,public=read_public('?publication='+sha(payload)+'-'+str(attempt))
            if canonical(public)==canonical(feed):break
        except Exception:
            if attempt==7:raise
        if attempt==7:raise ValueError('Published feed could not be verified publicly')
        time.sleep(3)
    report={'published':True,'mainWindows':VERSION,'mainAndroid':VERSION,'otherAppEntriesUnchanged':True,
            'testedSourceCommit':SOURCE,'testedWorkflowRun':RUN,'packageDownloadsVerified':True,'feed':FEED,
            'release':f'https://github.com/{REPO}/releases/tag/{TAG}'}
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args();publish(args.directory)
