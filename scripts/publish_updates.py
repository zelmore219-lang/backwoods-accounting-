"""Publish verified versioned packages, then update the public feed last."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import urllib.error
from build_update_release import REPO, sha

FEED=f'https://github.com/{REPO}/releases/download/app-updates/backwoods-updates.json'

def gh(*args):return subprocess.check_output(['gh',*args,'--repo',REPO],text=True).strip()
def release(tag):
    # Tag endpoints omit drafts; list authenticated releases so interrupted
    # uploads can resume the existing draft rather than creating another one.
    page=1
    while True:
        values=json.loads(subprocess.check_output(['gh','api',f'repos/{REPO}/releases?per_page=100&page={page}'],text=True))
        for value in values:
            if value['tag_name']==tag:return value
        if len(values)<100:return None
        page+=1
def create_release(tag,target,title,notes):
    # Use the creation response directly: newly created drafts may not appear
    # in the release listing immediately.
    payload={'tag_name':tag,'target_commitish':target,'name':title,'body':notes,'draft':True,'prerelease':True}
    return json.loads(subprocess.check_output(['gh','api','--method','POST',f'repos/{REPO}/releases','--input','-'],input=json.dumps(payload),text=True))
def verify_assets(value,files):
    assets={a['name']:a for a in value['assets']}
    for p in files:
        a=assets.get(p.name)
        if not a or a['state']!='uploaded' or a['size']!=p.stat().st_size or a.get('digest')!='sha256:'+sha(p):raise ValueError('Uploaded asset did not verify: '+p.name)

def publish(tag,directory):
    feed=json.loads((directory/'backwoods-updates.json').read_text())
    packages=[]
    if feed.get('schemaVersion')!=1 or set(feed['apps'])!={'main','vendor','accounting'}:raise ValueError('Incomplete update feed')
    for app in feed['apps'].values():
        for platform in ['windows','android']:
            artifact=app[platform];prefix=f'https://github.com/{REPO}/releases/download/{tag}/'
            if not artifact['url'].startswith(prefix):raise ValueError('Update artifact points outside this versioned release')
            name=artifact['url'][len(prefix):]
            if Path(name).name!=name:raise ValueError('Invalid artifact filename')
            p=directory/name
            if sha(p)!=artifact['sha256'] or p.stat().st_size!=artifact['size']:raise ValueError('Artifact checksum mismatch: '+name)
            packages.append(p)
    try:
        with urllib.request.urlopen(FEED,timeout=30) as r:previous=json.load(r)
    except urllib.error.HTTPError as e:
        if e.code!=404:raise
        previous=None
    if previous:
        for kind,app in feed['apps'].items():
            for platform in ['windows','android']:
                old=previous['apps'][kind][platform];new=app[platform]
                old_version=tuple(map(int,old['version'].split('.')));new_version=tuple(map(int,new['version'].split('.')))
                if new_version<old_version or (new_version==old_version and new['sha256']!=old['sha256']):raise ValueError(f'{kind} {platform}: bump the version before publishing changed packages; rollback is blocked')
    files=[*packages,directory/'backwoods-updates.json',directory/'SHA256SUMS.txt']
    current=release(tag)
    if current is None:
        current=create_release(tag,feed['sourceCommit'],'Backwoods app updates '+tag,(directory/'RELEASE_NOTES.md').read_text())
    existing={a['name']:a for a in current['assets']}
    for p in files:
        if p.name in existing:
            verify_assets(current,[p])
        elif current['draft']:gh('release','upload',tag,str(p))
        else:raise ValueError('Published release is immutable; choose a new release tag')
    verify_assets(release(tag),files)
    gh('release','edit',tag,'--draft=false','--prerelease','--latest=false')
    channel=release('app-updates')
    if channel is None:channel=create_release('app-updates',feed['sourceCommit'],'Backwoods automatic update feed','Public update metadata for Main, Vendor and Business Accounting. Versioned packages are linked from backwoods-updates.json.')
    gh('release','upload','app-updates',str(directory/'backwoods-updates.json'),'--clobber')
    verify_assets(release('app-updates'),[directory/'backwoods-updates.json'])
    gh('release','edit','app-updates','--draft=false','--prerelease','--latest=false')
    print(f'https://github.com/{REPO}/releases/tag/{tag}')
    print('Public updater feed: '+FEED)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--tag',required=True);p.add_argument('--directory',type=Path,required=True);args=p.parse_args();publish(args.tag,args.directory)
