"""Reproducible application update for the supplied 64-bit Python 3.14 shell."""
import argparse,hashlib,json,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build(out,wheels=None):
 out=out.resolve();out.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='production-update-') as tmp:
  temp=Path(tmp);stage=temp/'update';app=stage/'application'
  shutil.copytree(ROOT/'production',app,ignore=shutil.ignore_patterns('__pycache__','*.db','*.db-*','.venv','vendor','UPDATE-*','CONNECT-*'))
  for script in (ROOT/'production').iterdir():
   if script.is_file() and script.name.startswith(('UPDATE-','CONNECT-')):shutil.copy2(script,stage/script.name)
  shutil.copy2(ROOT/'docs/PRODUCTION-CONNECTIONS.md',stage/'PRODUCTION-CONNECTIONS.md')
  if wheels is None:
   wheels=temp/'wheels'
   subprocess.run([sys.executable,'-m','pip','download','--dest',str(wheels),'--only-binary=:all:','--platform','win_amd64','--python-version','314','--implementation','cp','--abi','cp314','cryptography==50.0.0','cffi==2.1.1','pycparser==3.12'],check=True)
  vendor=app/'vendor';vendor.mkdir()
  packages=list(Path(wheels).glob('*.whl'))
  if not any(p.name.startswith('cryptography-50.0.0-') for p in packages) or not any(p.name.startswith('cffi-') and 'cp314' in p.name for p in packages):raise ValueError('Expected Windows Python 3.14 cryptography wheels')
  provenance=[]
  for package in packages:
   with zipfile.ZipFile(package) as z:
    for name in z.namelist():
     if not (vendor/name).resolve().is_relative_to(vendor.resolve()):raise ValueError('Unsafe wheel path')
    z.extractall(vendor)
   provenance.append({'file':package.name,'sha256':hashlib.file_digest(package.open('rb'),'sha256').hexdigest()})
  (stage/'DEPENDENCIES.json').write_text(json.dumps(provenance,indent=2)+'\n')
  manifest={p.relative_to(stage).as_posix():hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in stage.rglob('*') if p.is_file()}
  (stage/'SHA256-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
  archive=Path(shutil.make_archive(str(out/'Backwoods-Production-Connected-Update'),'zip',stage))
  hash_=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest();archive.with_suffix('.zip.sha256').write_text(hash_+'  '+archive.name+'\n')
  print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':hash_}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'dist/production');p.add_argument('--wheels',type=Path);a=p.parse_args();build(a.out,a.wheels)
