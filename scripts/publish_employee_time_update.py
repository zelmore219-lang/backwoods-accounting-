"""Publish the exact accepted Accounting Windows installer; retain other feeds."""
import argparse,copy,hashlib,json,os,subprocess,tempfile,time,urllib.request
from pathlib import Path
REPO='zelmore219-lang/backwoods-accounting-'
SOURCE='e707c0d86629175efee50088c0fb6cc4dec6b3ec'
RUN=43615406895
VERSION='1.0.7'
NAME='Backwoods-Business-Accounting-Setup-'+VERSION+'.exe'
TAG='accounting-'+VERSION
FEED='https://github.com/'+REPO+'/releases/download/app-updates/backwoods-updates.json'

def api(path):return json.loads(subprocess.check_output(['gh','api','repos/'+REPO+'/'+path],text=True))
def mutate(method,path,value):return json.loads(subprocess.check_output(['gh','api','--method',method,'repos/'+REPO+'/'+path,'--input','-'],input=json.dumps(value),text=True))
def public(url):
 with urllib.request.urlopen(url,timeout=180) as response:return response.read()
def digest(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def release(tag):return next((value for value in api('releases?per_page=100') if value['tag_name']==tag),None)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
 run=api('actions/runs/'+str(RUN));jobs=api('actions/runs/'+str(RUN)+'/jobs')['jobs']
 assert run['head_sha']==SOURCE and run['status']=='completed' and run['conclusion']=='success'
 assert any(job['name']=='employee-time' and job['status']=='completed' and job['conclusion']=='success' for job in jobs)
 staged=release('accounting-time-ci-'+SOURCE);assert staged and staged['draft']
 asset=next(value for value in staged['assets'] if value['name']==NAME);expected=asset['digest'].removeprefix('sha256:')
 with tempfile.TemporaryDirectory() as folder:
  folder=Path(folder);installer=folder/NAME
  with installer.open('wb') as output:subprocess.run(['gh','api','repos/'+REPO+'/releases/assets/'+str(asset['id']),'-H','Accept: application/octet-stream'],stdout=output,check=True)
  assert installer.stat().st_size==asset['size'] and digest(installer)==expected
  with installer.open('rb') as stream:assert stream.read(2)==b'MZ'
  original_bytes=public(FEED);original=json.loads(original_bytes);updated=copy.deepcopy(original)
  old=original['apps']['accounting']['windows'];assert tuple(map(int,old['version'].split('.')))<=tuple(map(int,VERSION.split('.')))
  entry={'version':VERSION,'url':'https://github.com/'+REPO+'/releases/download/'+TAG+'/'+NAME,'sha256':expected,'size':asset['size']}
  if old['version']==VERSION:assert old==entry
  updated['apps']['accounting']['windows']=entry
  updated['apps']['accounting']['notes']='Windows 1.0.7 imports approved Employee hours, estimated gross wages and PTO by department for payroll review, with duplicate prevention. Android remains on its existing signed version.'
  updated.update(sourceCommit=SOURCE,updatedApps=['accounting'])
  assert updated['apps']['main']==original['apps']['main'] and updated['apps']['vendor']==original['apps']['vendor']
  assert updated['apps']['accounting']['android']==original['apps']['accounting']['android']
  feed_release=release('app-updates');feed_asset=next(value for value in feed_release['assets'] if value['name']=='backwoods-updates.json')
  assert feed_asset['digest']=='sha256:'+hashlib.sha256(original_bytes).hexdigest()
  print(json.dumps({'version':VERSION,'source':SOURCE,'acceptedRun':RUN,'sha256':expected,'size':asset['size'],'main':original['apps']['main']['windows']['version'],'vendor':original['apps']['vendor']['windows']['version'],'androidPreserved':True,'publish':args.publish}),flush=True)
  if not args.publish:return
  target=release(TAG)
  if target and not target['draft']:
   prior=next(value for value in target['assets'] if value['name']==NAME);assert prior['digest']==asset['digest'] and prior['size']==asset['size']
  else:
   if not target:target=mutate('POST','releases',{'tag_name':TAG,'target_commitish':SOURCE,'draft':True,'name':'Backwoods Business Accounting '+VERSION,'body':Path('docs/EMPLOYEE-TIME-1.0.7.md').read_text(encoding='utf-8')})
   sums=folder/'SHA256SUMS.txt';sums.write_text(expected+'  '+NAME+'\n')
   provenance=folder/'release-source.json';provenance.write_text(json.dumps({'sourceRepository':REPO,'sourceSha':SOURCE,'windowsAcceptanceRun':RUN,'version':VERSION,'sha256':expected,'bytes':asset['size'],'platform':'Windows','android':'Existing signed entry preserved'},indent=2)+'\n')
   subprocess.run(['gh','release','upload',TAG,str(installer),str(sums),str(provenance),'docs/EMPLOYEE-TIME-1.0.7.md','--repo',REPO,'--clobber'],check=True)
   ready=api('releases/'+str(target['id']));remote=next(value for value in ready['assets'] if value['name']==NAME)
   assert remote['digest']==asset['digest'] and remote['size']==asset['size']
   mutate('PATCH','releases/'+str(target['id']),{'draft':False,'prerelease':False,'make_latest':'false'})
  failure=None
  for delay in [0,3,6,12,24]:
   if delay:time.sleep(delay)
   try:
    raw=public(entry['url']);assert len(raw)==asset['size'] and hashlib.sha256(raw).hexdigest()==expected;failure=None;break
   except Exception as error:failure=error
  if failure:raise failure
  latest=public(FEED)
  if json.loads(latest)!=updated:
   assert latest==original_bytes,'Feed changed concurrently; retain the installer and review the latest feed before updating'
   current=api('releases/'+str(feed_release['id']));current_asset=next(value for value in current['assets'] if value['name']=='backwoods-updates.json')
   assert current_asset['digest']==feed_asset['digest']
   path=folder/'backwoods-updates.json';path.write_text(json.dumps(updated,indent=2)+'\n')
   subprocess.run(['gh','release','upload','app-updates',str(path),'--repo',REPO,'--clobber'],check=True)
  print('Published accepted Accounting Windows update; Main, Vendor and signed Android entries preserved.',flush=True)

if __name__=='__main__':main()
