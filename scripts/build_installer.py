"""Build a real per-user Windows installer without executing Windows code.

Electron-builder produces the application directory. The verified NSIS compiler
builds a conventional installer; its uninstaller is written on the target PC.
Uninstall removes only the packaged file manifest, preserving unrelated files.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def q(value):return str(value).replace('$','$$').replace('"','$\\"')


def build(builder,nsis,skip_pack=False):
    env=os.environ.copy()
    if env.get('HTTPS_PROXY'):
        env['ELECTRON_GET_USE_PROXY']='1'
        env['GLOBAL_AGENT_HTTPS_PROXY']=env['HTTPS_PROXY']
        env['GLOBAL_AGENT_HTTP_PROXY']=env.get('HTTP_PROXY',env['HTTPS_PROXY'])
    if not skip_pack:
        subprocess.run([str(builder),'--config','desktop/electron-builder.yml','--win','--x64','--dir','--publish','never'],cwd=ROOT,env=env,check=True)
    app_dir=ROOT/'dist/windows/win-unpacked'
    if not (app_dir/'Backwoods Business Accounting.exe').exists():raise ValueError('Packaged application is missing')
    if not (app_dir/'resources/python/python.exe').exists():raise ValueError('Bundled Windows Python runtime is missing')
    version=json.loads((ROOT/'desktop/package.json').read_text())['version']
    subprocess.run(['node',str(ROOT/'scripts/set_windows_icon.cjs'),str(app_dir/'Backwoods Business Accounting.exe'),str(ROOT/'desktop/icon.ico'),'Backwoods Business Accounting',version],check=True)
    output=ROOT/f'dist/windows/Backwoods-Business-Accounting-Setup-{version}.exe'
    files=sorted(p for p in app_dir.rglob('*') if p.is_file())
    manifest={p.relative_to(app_dir).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (ROOT/'dist/windows/installed-file-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    deletes='\n'.join('  Delete "$INSTDIR\\'+q(p.relative_to(app_dir).as_posix().replace('/','\\'))+'"' for p in files)
    directories=sorted([p for p in app_dir.rglob('*') if p.is_dir()],key=lambda p:len(p.parts),reverse=True)
    removes='\n'.join('  RMDir "$INSTDIR\\'+q(p.relative_to(app_dir).as_posix().replace('/','\\'))+'"' for p in directories)
    script=f'''
Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
Name "Backwoods Business Accounting"
OutFile "{q(output)}"
InstallDir "$LOCALAPPDATA\\Programs\\Backwoods Business Accounting"
InstallDirRegKey HKCU "Software\\BackwoodsBusinessAccounting" "InstallDir"
RequestExecutionLevel user
SetCompressor zlib
ShowInstDetails show
ShowUninstDetails show
!define MUI_ICON "{q(ROOT/'desktop/icon.ico')}"
!define MUI_UNICON "{q(ROOT/'desktop/icon.ico')}"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\\Backwoods Business Accounting.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open Backwoods Business Accounting"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH
!insertmacro MUI_LANGUAGE "English"
VIProductVersion "{version}.0"
VIAddVersionKey /LANG=1033 "ProductName" "Backwoods Business Accounting"
VIAddVersionKey /LANG=1033 "CompanyName" "Backwoods Brew"
VIAddVersionKey /LANG=1033 "FileDescription" "Backwoods Business Accounting Installer"
VIAddVersionKey /LANG=1033 "FileVersion" "{version}"
VIAddVersionKey /LANG=1033 "ProductVersion" "{version}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Backwoods Brew"

Function .onInit
  ${{IfNot}} ${{RunningX64}}
    MessageBox MB_OK "This installer requires 64-bit Windows."
    Quit
  ${{EndIf}}
  MessageBox MB_OKCANCEL "Before installing or upgrading, close Backwoods Business Accounting, including its system-tray process. Your company records in Local AppData are preserved." IDOK continueInstall
  Quit
  continueInstall:
FunctionEnd

Function EnsureAccountingWritable
  retryAccountingClose:
  IfFileExists "$INSTDIR\\Backwoods Business Accounting.exe" 0 accountingWritable
  ; Open the existing executable exclusively without changing its contents.
  ; A running tray process prevents this write handle from being acquired.
  System::Call 'kernel32::CreateFileW(w "$INSTDIR\\Backwoods Business Accounting.exe", i 0x40000000, i 0, p 0, i 3, i 0, p 0) p .r0'
  StrCmp $0 -1 accountingLocked
  System::Call 'kernel32::CloseHandle(p r0)'
  Goto accountingWritable
  accountingLocked:
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "Windows cannot replace Backwoods Business Accounting.exe yet.$\\r$\\n$\\r$\\nSave your work, choose File > Quit or Exit from the system-tray icon, then click Retry. Closing the window may leave the app running in the tray.$\\r$\\n$\\r$\\nIf it is already closed, check that your Windows account can write to this installation folder. No program files have been replaced." IDRETRY retryAccountingClose
  Abort
  accountingWritable:
FunctionEnd

Section "Business Accounting" SEC_APP
  SetShellVarContext current
  Call EnsureAccountingWritable
  SetOutPath "$INSTDIR"
  File /r "{q(app_dir)}/*"
  WriteUninstaller "$INSTDIR\\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\\Backwoods Business Accounting"
  CreateShortcut "$SMPROGRAMS\\Backwoods Business Accounting\\Business Accounting.lnk" "$INSTDIR\\Backwoods Business Accounting.exe"
  CreateShortcut "$DESKTOP\\Backwoods Business Accounting.lnk" "$INSTDIR\\Backwoods Business Accounting.exe"
  WriteRegStr HKCU "Software\\BackwoodsBusinessAccounting" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsBusinessAccounting" "DisplayName" "Backwoods Business Accounting"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsBusinessAccounting" "DisplayVersion" "{version}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsBusinessAccounting" "Publisher" "Backwoods Brew"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsBusinessAccounting" "UninstallString" '$\\"$INSTDIR\\Uninstall.exe$\\"'
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsBusinessAccounting" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsBusinessAccounting" "NoModify" 1
  WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsBusinessAccounting" "NoRepair" 1
SectionEnd

Function un.onInit
  MessageBox MB_OKCANCEL "Close Backwoods Business Accounting, including its system-tray process, before uninstalling. Your company database and payroll connection remain in Local AppData." IDOK continueUninstall
  Abort
  continueUninstall:
FunctionEnd

Section "Uninstall"
  SetShellVarContext current
{deletes}
  Delete "$INSTDIR\\Uninstall.exe"
{removes}
  RMDir "$INSTDIR"
  Delete "$DESKTOP\\Backwoods Business Accounting.lnk"
  Delete "$SMPROGRAMS\\Backwoods Business Accounting\\Business Accounting.lnk"
  RMDir "$SMPROGRAMS\\Backwoods Business Accounting"
  DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsBusinessAccounting"
  DeleteRegKey HKCU "Software\\BackwoodsBusinessAccounting"
SectionEnd
'''
    nsi=ROOT/'dist/windows/backwoods-installer.nsi';nsi.write_text(script,encoding='utf-8')
    env['NSISDIR']=str(nsis.parent.parent)
    subprocess.run([str(nsis),'-V2',str(nsi)],cwd=ROOT,env=env,check=True)
    if output.read_bytes()[:2]!=b'MZ':raise ValueError('Installer is not a Windows executable')
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.exe.sha256').write_text(digest+'  '+output.name+'\n')
    print(json.dumps({'installer':str(output),'bytes':output.stat().st_size,'sha256':digest}))
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--builder',type=Path,default=ROOT/'desktop/node_modules/.bin/electron-builder')
    parser.add_argument('--nsis',type=Path,required=True)
    parser.add_argument('--skip-pack',action='store_true')
    args=parser.parse_args();build(args.builder,args.nsis,args.skip_pack)
