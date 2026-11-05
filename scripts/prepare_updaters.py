"""Copy the shared Windows updater into each packaged Electron app."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
def prepare():
    source=ROOT/'connectors/updater'
    for target in [ROOT/'desktop/updater',*(ROOT/'source-app-updates'/kind/'electron/updater' for kind in ['main','vendor'])]:
        target.mkdir(parents=True,exist_ok=True)
        for p in source.iterdir():
            if p.is_file():shutil.copy2(p,target/p.name)
if __name__=='__main__':prepare()
