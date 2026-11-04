"""Generate separate Windows installers for both connected source editions.

Uses the already verified Electron app directories and the standard NSIS compiler;
does not require Wine and does not include user profiles or accounting databases.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def q(value):return str(value).replace('$','$$').replace('"','$\\"')


def build(kind,builder,nsis,skip_pack=False):
    project=ROOT/'source-app-updates'/kind
    package=json.loads((project/'package.json').read_text())
    env=os.environ.copy()
    if env.get('HTTPS_PROXY'):
        env['ELECTRON_GET_USE_PROXY']='1';env['GLOBAL_AGENT_HTTPS_PROXY']=env['HTTPS_PROXY'];env['GLOBAL_AGENT_HTTP_PROXY']=env.get('HTTP_PROXY',env['HTTPS_PROXY'])
    if not skip_pack:subprocess.run([str(builder),'--projectDir',str(project),'--win','--x64','--dir','--publish','never'],cwd=ROOT,env=env,check=True)
    folder=ROOT/'dist/source-app-updates'/kind
    app_dir=folder/'win-unpacked';name=package['productName'];version=package['version'];exe=name+'.exe'
    if not (app_dir/exe).exists():raise ValueError('Windows application directory is missing: '+str(app_dir))
    output=folder/('Backwoods-Brew-Connected' if kind=='main' else 'Backwoods-Vendor-Ordering-Connected')
    output=Path(str(output)+'-Setup-'+version+'.exe')
    icon=project/('assets/icon.ico' if kind=='main' else 'dist/icons/app.ico')
    key='BackwoodsBrewConnected' if kind=='main' else 'BackwoodsVendorOrderingConnected'
    files=sorted(p for p in app_dir.rglob('*') if p.is_file())
    manifest={p.relative_to(app_dir).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (folder/'installed-file-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    deletes='\n'.join('  Delete "$INSTDIR\\'+q(p.relative_to(app_dir).as_posix().replace('/','\\'))+'"' for p in files)
    dirs=sorted([p for p in app_dir.rglob('*') if p.is_dir()],key=lambda p:len(p.parts),reverse=True)
    removes='\n'.join('  RMDir "$INSTDIR\\'+q(p.relative_to(app_dir).as_posix().replace('/','\\'))+'"' for p in dirs)
    script=f'''
Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
Name "{q(name)}"
OutFile "{q(output)}"
InstallDir "$LOCALAPPDATA\\Programs\\{q(name)}"
InstallDirRegKey HKCU "Software\\{key}" "InstallDir"
RequestExecutionLevel user
SetCompressor zlib
ShowInstDetails show
ShowUninstDetails show
!define MUI_ICON "{q(icon)}"
!define MUI_UNICON "{q(icon)}"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\\{q(exe)}"
!define MUI_FINISHPAGE_RUN_TEXT "Open {q(name)}"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "English"
VIProductVersion "{version}.0"
VIAddVersionKey /LANG=1033 "ProductName" "{q(name)}"
VIAddVersionKey /LANG=1033 "CompanyName" "Backwoods Brew"
VIAddVersionKey /LANG=1033 "FileDescription" "Accounting-connected source app installer"
VIAddVersionKey /LANG=1033 "FileVersion" "{version}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Backwoods Brew"
Function .onInit
  ${{IfNot}} ${{RunningX64}}
    MessageBox MB_OK "This installer requires 64-bit Windows."
    Quit
  ${{EndIf}}
  MessageBox MB_OKCANCEL "Back up your source app and close it before the first connected launch. This installs a separate Connected edition; it copies a detected old local profile and keeps the original intact." IDOK proceed
  Quit
  proceed:
FunctionEnd
Section "{q(name)}"
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "{q(app_dir)}/*"
  WriteUninstaller "$INSTDIR\\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\\{q(name)}"
  CreateShortcut "$SMPROGRAMS\\{q(name)}\\{q(name)}.lnk" "$INSTDIR\\{q(exe)}"
  CreateShortcut "$DESKTOP\\{q(name)}.lnk" "$INSTDIR\\{q(exe)}"
  WriteRegStr HKCU "Software\\{key}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{key}" "DisplayName" "{q(name)}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{key}" "DisplayVersion" "{version}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{key}" "Publisher" "Backwoods Brew"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{key}" "UninstallString" '$\\"$INSTDIR\\Uninstall.exe$\\"'
SectionEnd
Section "Uninstall"
  SetShellVarContext current
{deletes}
  Delete "$INSTDIR\\Uninstall.exe"
{removes}
  RMDir "$INSTDIR"
  Delete "$DESKTOP\\{q(name)}.lnk"
  Delete "$SMPROGRAMS\\{q(name)}\\{q(name)}.lnk"
  RMDir "$SMPROGRAMS\\{q(name)}"
  DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{key}"
  DeleteRegKey HKCU "Software\\{key}"
SectionEnd
'''
    nsi=folder/'installer.nsi';nsi.write_text(script)
    env['NSISDIR']=str(nsis.parent.parent)
    subprocess.run([str(nsis),'-V2',str(nsi)],env=env,cwd=ROOT,check=True)
    if output.read_bytes()[:2]!=b'MZ':raise ValueError('Installer PE header is missing')
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.exe.sha256').write_text(digest+'  '+output.name+'\n')
    print(json.dumps({'app':kind,'installer':str(output),'bytes':output.stat().st_size,'sha256':digest}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('app',choices=['main','vendor']);p.add_argument('--builder',type=Path,required=True);p.add_argument('--nsis',type=Path,required=True);p.add_argument('--skip-pack',action='store_true')
    a=p.parse_args();build(a.app,a.builder,a.nsis,a.skip_pack)
