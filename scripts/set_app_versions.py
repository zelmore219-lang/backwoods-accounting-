"""Set release versions consistently for Windows and Android builds."""
import argparse
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
def set_version(kind,version):
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Use a numeric version such as 1.0.5')
    major,minor,patch=map(int,version.split('.'))
    if major>999 or minor>99 or patch>99:raise ValueError('Version components exceed the Android version-code scheme')
    code=major*10000+minor*100+patch
    projects=[ROOT/'desktop'] if kind=='accounting' else [ROOT/'source-app-updates'/kind,ROOT/'android-apps'/kind]
    for project in projects:
        for name in ['package.json','package-lock.json']:
            p=project/name;value=json.loads(p.read_text());value['version']=version
            if 'packages' in value:value['packages']['']['version']=version
            p.write_text(json.dumps(value,indent=2)+'\n')
    android=ROOT/'android-apps'/kind
    p=android/'android/app/build.gradle';s=p.read_text();s=re.sub(r'versionCode \d+','versionCode '+str(code),s,count=1);s=re.sub(r'versionName [\'"][^\'"]+[\'"]',"versionName '"+version+"'",s,count=1);p.write_text(s)
    p=android/'build-metadata.json'
    if p.exists():value=json.loads(p.read_text());value.update(versionName=version,versionCode=code);p.write_text(json.dumps(value,indent=2)+'\n')
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for kind in ['accounting','vendor','main']:parser.add_argument('--'+kind,default='')
    args=parser.parse_args()
    for kind,version in vars(args).items():
        if version:set_version(kind,version)
