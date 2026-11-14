"""Keep verified CI downloads in private draft releases, without Actions storage."""
import argparse,glob,hashlib,json,os,subprocess,time,urllib.parse,urllib.request
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--prefix',required=True);parser.add_argument('paths',nargs='+');args=parser.parse_args()
repo=os.environ['GITHUB_REPOSITORY'];sha=os.environ['GITHUB_SHA'];token=os.environ.get('GH_TOKEN') or os.environ['GITHUB_TOKEN'];tag=args.prefix+'-'+sha
assert len(sha)==40 and all(c in '0123456789abcdef' for c in sha)
def api(method,path,payload=None):
 command=['gh','api','--method',method,'repos/'+repo+'/'+path]
 if payload is not None:command+=['--input','-']
 raw=subprocess.check_output(command,input=json.dumps(payload) if payload is not None else None,text=True);return json.loads(raw) if raw.strip() else None
release=next((item for item in api('GET','releases?per_page=100') if item['tag_name']==tag),None)
if not release:
 try:release=api('POST','releases',{'tag_name':tag,'target_commitish':sha,'draft':True,'name':args.prefix+' '+sha[:12],'body':'Private build staging. These files are not published app updates. Source: '+sha})
 except subprocess.CalledProcessError:
  for _ in range(10):
   release=next((item for item in api('GET','releases?per_page=100') if item['tag_name']==tag),None)
   if release:break
   time.sleep(2)
  if not release:raise
assert release['draft'],'Build staging must remain private/draft'
files=sorted({str(Path(file).resolve()) for pattern in args.paths for file in glob.glob(pattern,recursive=True) if Path(file).is_file()})
if not files:raise SystemExit('No build files were staged')
for filename in files:
 file=Path(filename);expected=hashlib.file_digest(file.open('rb'),'sha256').hexdigest()
 current=api('GET','releases/'+str(release['id']));asset=next((item for item in current['assets'] if item['name']==file.name),None)
 if asset:
  if asset.get('digest')=='sha256:'+expected and asset['size']==file.stat().st_size:continue
  api('DELETE','releases/assets/'+str(asset['id']))
 url='https://uploads.github.com/repos/'+repo+'/releases/'+str(release['id'])+'/assets?'+urllib.parse.urlencode({'name':file.name})
 with file.open('rb') as stream:
  request=urllib.request.Request(url,data=stream,method='POST',headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/octet-stream','Content-Length':str(file.stat().st_size),'User-Agent':'Backwoods-private-build-staging'})
  with urllib.request.urlopen(request,timeout=300) as response:uploaded=json.load(response)
 assert uploaded['size']==file.stat().st_size and uploaded.get('digest')=='sha256:'+expected,'Private build upload integrity mismatch'
 print(json.dumps({'staged':file.name,'sha256':expected,'size':file.stat().st_size,'releaseId':release['id'],'sourceSha':sha}))
