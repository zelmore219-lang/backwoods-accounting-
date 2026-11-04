"""Create reviewable connected copies of the exact uploaded app versions.

Never overwrites input apps. Does not install into, or change, a live installation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

ROOT=Path(__file__).resolve().parents[1]
PROFILE_CONFIG={
    'main':{'source':'main','originalLabel':'Backwoods Brew','connectedProfile':'Backwoods Brew Connected','originalProfiles':['Backwoods Brew','backwoods-brew-pc'],'originalExecutables':['Backwoods Brew.exe']},
    'vendor':{'source':'vendor','originalLabel':'Backwoods Vendor Ordering','connectedProfile':'Backwoods Vendor Ordering Connected','originalProfiles':['Backwoods Vendor Ordering','backwoods-vendor-ordering'],'originalExecutables':['Backwoods Vendor Ordering.exe']},
}


def extract_asar(archive,destination):
    destination=Path(destination).resolve()
    with open(archive,'rb') as stream:
        prelude=stream.read(16)
        if len(prelude)!=16:raise ValueError('Truncated ASAR')
        first,header_size,payload_size,json_size=struct.unpack('<4I',prelude)
        if first!=4 or header_size>10*1024*1024 or json_size>header_size or payload_size+4!=header_size:
            raise ValueError('Unsupported ASAR header')
        tree=json.loads(stream.read(json_size))
        base=8+header_size
        def walk(files,relative=Path()):
            for name,entry in files.items():
                target=(destination/relative/name).resolve()
                if not target.is_relative_to(destination):raise ValueError('Unsafe ASAR path')
                if 'files' in entry:walk(entry['files'],relative/name);continue
                if 'link' in entry or entry.get('unpacked'):raise ValueError('Linked/unpacked ASAR files need their companion resources')
                size=int(entry['size']);offset=int(entry['offset'])
                if min(size,offset)<0:raise ValueError('Invalid ASAR entry')
                stream.seek(base+offset);content=stream.read(size)
                if len(content)!=size:raise ValueError('Truncated ASAR content')
                integrity=entry.get('integrity')
                if integrity and (integrity.get('algorithm')!='SHA256' or hashlib.sha256(content).hexdigest()!=integrity.get('hash')):
                    raise ValueError('ASAR integrity check failed')
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        walk(tree['files'])


def pack_asar(directory,destination):
    tree={'files':{}};offset=0;contents=[]
    for file in sorted(Path(directory).rglob('*')):
        if not file.is_file():continue
        relative=file.relative_to(directory)
        node=tree['files']
        for part in relative.parts[:-1]:node=node.setdefault(part,{'files':{}})['files']
        content=file.read_bytes()
        node[relative.name]={'size':len(content),'offset':str(offset),
            'integrity':{'algorithm':'SHA256','hash':hashlib.sha256(content).hexdigest(),
                         'blockSize':4*1024*1024,'blocks':[hashlib.sha256(content[i:i+4*1024*1024]).hexdigest() for i in range(0,len(content),4*1024*1024)]}}
        contents.append(content);offset+=len(content)
    header=json.dumps(tree,separators=(',',':'),ensure_ascii=False).encode()
    padded=header+b'\0'*((-len(header))%4)
    header_buffer=struct.pack('<II',4+len(padded),len(header))+padded
    with open(destination,'wb') as output:
        output.write(struct.pack('<II',4,len(header_buffer)));output.write(header_buffer)
        for content in contents:output.write(content)


def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('Version-specific patch anchor missing or ambiguous: '+old[:100])
    return text.replace(old,new,1)


def common(destination,source,html):
    electron=destination/'electron'
    (electron/'business-accounting-config.json').write_text(json.dumps(PROFILE_CONFIG[source],indent=2)+'\n')
    shutil.copy2(ROOT/'connectors/desktop-feed.cjs',electron/'desktop-feed.cjs')
    shutil.copy2(ROOT/'connectors/connected-profile.cjs',electron/'connected-profile.cjs')
    main=electron/'main.cjs'
    lines=main.read_text().splitlines(keepends=True)
    lines.insert(1,"require('./connected-profile.cjs').prepareProfile({app,dialog}, require('./business-accounting-config.json'));\n")
    main.write_text(''.join(lines)+"\nrequire('./desktop-feed.cjs');\n")
    preload=electron/'preload.cjs'
    preload.write_text(preload.read_text()+"\nrequire('electron').contextBridge.exposeInMainWorld('businessAccounting', {status:()=>require('electron').ipcRenderer.invoke('business-accounting:status')});\n")
    shutil.copy2(ROOT/'connectors/source-panel.js',html.parent/'business-accounting-panel.js')
    html.write_text(replace_once(html.read_text(),'</body>','<script src="./business-accounting-panel.js"></script></body>'))


MAIN_HOOK=r'''
  window.__bwAccountingSnapshot = () => {
    if (!a || a.active===false || !['owner','admin','administrator'].includes(String(a.role||'').toLowerCase())) return null;
    const keys=['accounts','orders','invoices','bills','expenses','journalEntries','payrollRuns','salesTaxPayments','payrollTaxPayments','wasteLogs','greenCoffeeLots','roastBatches','voids','refunds','receiptAttachments','payments','inventory','products','stores'];
    const data={};
    for(const key of keys) data[key]=(Array.isArray(r[key])?r[key]:[]).filter(row=>!['vendor-ordering','vendor'].includes(String(row.sourceSystem||row.sourceApp||'').toLowerCase()));
    // Compute with the complete native state, while exporting only selected
    // financial fields. Native settings stay in memory and are not transmitted.
    data.generalLedger=Ga({...r,...data});
    data.products=data.products.map(p=>{const {image,photo,photoDataUrl,...rest}=p;return rest;});
    return {schemaVersion:1,app:'Backwoods Brew',type:'business-accounting-feed',data};
  };
'''

VENDOR_HOOK=r'''
window.__bwAccountingSnapshot=()=>{
 if(!n||n.role!=='owner'||n.active===false||!r)return null;
 const data={};
 for(const key of ['company','customers','products','suppliers','purchaseOrders','purchaseReceipts','supplierInvoices','orders','credits','payments','inventoryMovements','driverSettlements'])data[key]=key==='company'?{name:e.company?.name||''}:e[key]||[];
 data.products=data.products.map(p=>{const {photoDataUrl,...rest}=p;return rest;});
 return {schemaVersion:1,app:'Backwoods Vendor Ordering',type:'business-accounting-feed',data};
};
'''


def build(main_dir,vendor_asar,output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Output directory already exists; choose a new one to preserve previous files')
    output.mkdir(parents=True)
    main_dest=output/'Backwoods-Brew-connected'
    vendor_dest=output/'Vendor-Ordering-connected'
    shutil.copytree(main_dir,main_dest,ignore=shutil.ignore_patterns('node_modules','.git','dist'))
    extract_asar(vendor_asar,vendor_dest)
    package=json.loads((main_dest/'package.json').read_text())
    vendor_package=json.loads((vendor_dest/'package.json').read_text())
    if package.get('version')!='8.2.0' or vendor_package.get('version')!='4.1.0':
        raise ValueError('These adapters support the supplied Main 8.2.0 and Vendor 4.1.0 versions only')
    main_bundle=main_dest/'www/assets/main-CnsZnSKS.js'
    original=main_bundle.read_text()
    patched=replace_once(original,'[w, I] = j.useState(!1);','[w, I] = j.useState(!1);\n'+MAIN_HOOK)
    main_bundle.write_text(patched)
    # Always load bundled assets when testing this copied source, without a Vite server.
    main_process=main_dest/'electron/main.cjs'
    s=main_process.read_text()
    s=replace_once(s,'win.loadURL("http://127.0.0.1:5173");','win.loadFile(path.join(__dirname, "..", "www", "index.html"));')
    main_process.write_text(s)
    common(main_dest,'main',main_dest/'www/index.html')
    bundle=vendor_dest/'dist/assets/index-CWBa4KXx.js'
    s=bundle.read_text()
    anchor='g=(n==null?void 0:n.active)!==!1&&(n==null?void 0:n.uid)&&n.role!=="pending";q.useEffect'
    s=replace_once(s,anchor,anchor[:-len('q.useEffect')]+VENDOR_HOOK+'q.useEffect')
    # Capture future inventory costs where the supplied build omitted them.
    s=replace_once(s,'type:"delivery",quantity:-Je,reference:r.invoiceNumber',
                   'type:"delivery",quantity:-Je,unitCost:Number(Ce.cost||0),accountingCostCaptured:true,reference:r.invoiceNumber')
    s=replace_once(s,'type:"credit_return",quantity:qe,reference:r.invoiceNumber',
                   'type:"credit_return",quantity:qe,unitCost:Number((xe.products.find(p=>p.id===Z.productId)||{}).cost||0),accountingCostCaptured:true,reference:r.invoiceNumber')
    s=replace_once(s,'type:`return_${yn}`,quantity:Bt,reference:r.invoiceNumber',
                   'type:`return_${yn}`,quantity:Bt,unitCost:Number(Ce.cost||0),accountingCostCaptured:true,reference:r.invoiceNumber')
    bundle.write_text(s)
    vendor_main=vendor_dest/'electron/main.cjs'
    s=replace_once(vendor_main.read_text(),"win.loadURL('http://localhost:5173')","win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))")
    vendor_main.write_text(s)
    common(vendor_dest,'vendor',vendor_dest/'dist/index.html')
    # The uploaded apps already contain bundled renderer dependencies. The Electron
    # main/preload code uses only Electron and Node built-ins; no npm runtime tree
    # was present in the supplied vendor ASAR.
    for destination,source,version in [(main_dest,'main','8.2.1'),(vendor_dest,'vendor','4.1.1')]:
        original_package=json.loads((destination/'package.json').read_text())
        connected_package={key:original_package[key] for key in ['name','author','type','main'] if key in original_package}
        connected_package.update({'version':version,'private':True,'productName':PROFILE_CONFIG[source]['connectedProfile'],
            'description':PROFILE_CONFIG[source]['originalLabel']+' with one-way Business Accounting connection','license':'UNLICENSED'})
        connected_package['build']={
            'appId':'com.backwoodsbrew.main.connected' if source=='main' else 'com.backwoodsbrew.vendor.connected',
            'productName':PROFILE_CONFIG[source]['connectedProfile'],'electronVersion':'45.2.2','asar':True,
            'directories':{'output':'../../dist/source-app-updates/'+source},
            'files':['electron/**/*','www/**/*','assets/**/*','src/**/*','package.json'] if source=='main' else ['electron/**/*','dist/**/*','package.json'],
            'win':{'target':['nsis'],'icon':'assets/icon.ico' if source=='main' else 'dist/icons/app.ico','signAndEditExecutable':False},
            'nsis':{'oneClick':False,'allowToChangeInstallationDirectory':True,'perMachine':False,'createDesktopShortcut':True,'createStartMenuShortcut':True,'deleteAppDataOnUninstall':False},
            'artifactName':('Backwoods-Brew-Connected' if source=='main' else 'Backwoods-Vendor-Ordering-Connected')+'-Setup-${version}.${ext}',
        }
        if source=='main':connected_package['scripts']={'verify':'node scripts/verify.cjs'}
        (destination/'package.json').write_text(json.dumps(connected_package,indent=2)+'\n')
        (destination/'ORIGINAL-PACKAGE.json').write_text(json.dumps(original_package,indent=2)+'\n')
        html=destination/('www/index.html' if source=='main' else 'dist/index.html')
        import re
        html.write_text(re.sub(r'<title>[^<]*</title>','<title>'+PROFILE_CONFIG[source]['connectedProfile']+'</title>',html.read_text(),count=1))
        if source=='vendor':
            process_file=destination/'electron/main.cjs'
            process_file.write_text(process_file.read_text().replace("path.join(__dirname, '..', 'public', 'icons', 'icon-512.png')","path.join(__dirname, '..', 'dist', 'icons', 'icon-512.png')"))
    pack_asar(main_dest,output/'main-connected.asar')
    pack_asar(vendor_dest,output/'vendor-connected.asar')
    manifest={}
    for name in ['main-connected.asar','vendor-connected.asar']:
        manifest[name]=hashlib.sha256((output/name).read_bytes()).hexdigest()
    (output/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'README.txt').write_text('''CONNECTED TEST COPIES — preserve your installed apps and data.

These are application archives, not Windows installers. The originals were not changed.
Installer-ready versions are Main 8.2.1 Connected and Vendor 4.1.1 Connected,
based on the uploaded Main 8.2.0 and Vendor 4.1.0 packages. Connected editions copy
the previous local profile on first launch and leave that original profile intact.
Back up both source apps before testing. A separate installation folder does not
isolate Electron user data. Use a separate Windows user or set
BACKWOODS_TEST_DATA_DIR to a disposable profile folder before launching the test
copy. Test with fictitious records and avoid live cloud writes. Close the test app,
and replace only its resources/app.asar with the matching connected archive named
app.asar. Never put the vendor archive into the main app or vice versa.
Electron fuses/signing may prevent archive replacement; use original build source
and a proper signed installer in that case. Do not disable integrity enforcement.

Open the source app, sign in as owner, open Business Accounting connection in the
lower-left corner, and enable Send to Business Accounting. Start the standalone
accounting app on the same computer. Review import status and any missing costs.
No source bookkeeping or Firebase documents are written by the connector.
The vendor copy additionally captures future delivery movement unit costs.

The connected archives have been structurally checked; Windows install, real logins,
cloud authorization and live-data transfer require testing on your own installation.
For Linux source-copy smoke tests, run an installed compatible Electron against
each connected directory. The copied main process loads its local bundled assets.
''')
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--main-dir',required=True,type=Path)
    parser.add_argument('--vendor-asar',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args()
    print(build(args.main_dir,args.vendor_asar,args.out))
