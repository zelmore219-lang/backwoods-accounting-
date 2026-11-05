"""Copy only accounting program files into the embedded Android runtime."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]

def prepare():
    target=ROOT/'.build-resources/android-python'
    if target.exists():shutil.rmtree(target)
    package=target/'accounting';package.mkdir(parents=True)
    for path in (ROOT/'accounting').iterdir():
        if path.is_file() and path.suffix in {'.py','.json'}:shutil.copy2(path,package/path.name)
    boot=ROOT/'android-apps/accounting/android_boot.py'
    if boot.exists():shutil.copy2(boot,target/'android_boot.py')
    assets=ROOT/'.build-resources/android-assets/accounting-web'
    if assets.exists():shutil.rmtree(assets)
    assets.mkdir(parents=True)
    for path in (ROOT/'web').iterdir():
        if path.is_file():shutil.copy2(path,assets/path.name)
    print('Prepared embedded accounting engine and web assets; no company data included.')

if __name__=='__main__':prepare()
