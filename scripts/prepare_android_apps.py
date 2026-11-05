"""Prepare Capacitor Android projects from the supplied, bundled source apps."""
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
PLUGINS={'@capacitor/core':'7.6.10','@capacitor/android':'7.6.10','@capacitor/app':'7.1.2',
         '@capacitor/browser':'7.0.5','@capacitor/filesystem':'7.1.9','@capacitor/share':'7.0.4','@capacitor/geolocation':'7.1.8'}


def prepare():
    for kind,name,app_id,version,code in [
        ('main','Backwoods Brew Connected','com.backwoodsbrew.main.connected','8.2.3',80203),
        ('vendor','Backwoods Vendor Connected','com.backwoodsbrew.vendor.connected','4.1.3',40103),
    ]:
        folder=ROOT/'android-apps'/kind
        folder.mkdir(parents=True,exist_ok=True)
        source=ROOT/'source-app-updates'/kind/('www' if kind=='main' else 'dist')
        if not (source/'index.html').exists():raise ValueError('Prepare the complete connected source app first: '+kind)
        web=folder/'web'
        if web.exists():shutil.rmtree(web)
        shutil.copytree(source,web)
        # This panel uses Electron's local filesystem bridge. Android accounting
        # snapshots use the authenticated Firebase transport on both platforms.
        panel=web/'business-accounting-panel.js'
        if panel.exists():panel.unlink()
        html=web/'index.html'
        html.write_text(html.read_text().replace('<script src="./business-accounting-panel.js"></script>',''))
        (folder/'package.json').write_text(json.dumps({'name':'backwoods-'+kind+'-android-connected','version':version,'private':True,
            'scripts':{'sync':'cap sync android'},'dependencies':PLUGINS,'devDependencies':{'@capacitor/cli':'7.6.10'}},indent=2)+'\n')
        (folder/'capacitor.config.json').write_text(json.dumps({'appId':app_id,'appName':name,'webDir':'web','server':{'androidScheme':'https','hostname':'localhost'},'android':{'allowMixedContent':False}},indent=2)+'\n')
        (folder/'build-metadata.json').write_text(json.dumps({'versionName':version,'versionCode':code,'source':kind,'accountingRoute':'authenticated Firebase accounting snapshots; automatic server ingestion after one-time deployment'},indent=2)+'\n')
    print('Prepared main and vendor Android web projects.')


if __name__=='__main__':prepare()
