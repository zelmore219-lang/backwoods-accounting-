"""Package the retained Production desktop app into a per-user Windows setup."""
import argparse,hashlib,json,os,shutil,subprocess,sys,urllib.request,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VERSION='1.0.0'
PYTHON_URL='https://www.python.org/ftp/python/3.14.0/python-3.14.0-embed-amd64.zip'
PYTHON_SHA='8d4d3590c10449d78aa4375f534e6d5f3027d67fdc362dd1a882279db6f90fdf'
WEBVIEW_URL='https://go.microsoft.com/fwlink/p/?LinkId=2124703'

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def q(value):return str(value).replace('$','$$').replace('"','$\\"')

def extract(archive,directory):
    with zipfile.ZipFile(archive) as source:
        for name in source.namelist():
            if not (directory/name).resolve().is_relative_to(directory.resolve()):raise ValueError('Unsafe package member')
        source.extractall(directory)

def build(nsis,update,runtime=None,bootstrapper=None,out=None):
    out=(out or ROOT/'dist/production-installer').resolve();out.mkdir(parents=True,exist_ok=True)
    payload=out/'payload';shutil.rmtree(payload,ignore_errors=True);app=payload/'Application';app.mkdir(parents=True)
    if runtime is None:
        runtime=out/'python-3.14.0.zip'
        if not runtime.exists():urllib.request.urlretrieve(PYTHON_URL,runtime)
    if sha(runtime)!=PYTHON_SHA:raise ValueError('The embedded Python runtime failed verification')
    unpacked=out/'update';shutil.rmtree(unpacked,ignore_errors=True);extract(update,unpacked)
    for name,digest in json.loads((unpacked/'SHA256-MANIFEST.json').read_text()).items():
        file=(unpacked/name).resolve()
        if not file.is_relative_to(unpacked.resolve()) or sha(file)!=digest:raise ValueError('Production update integrity failed')
    shutil.copytree(unpacked/'application',app/'app')
    for name in ['CONNECT-EXISTING-APPS.cmd','CONNECT-EXISTING-APPS.ps1','PRODUCTION-CONNECTIONS.md']:shutil.copy2(unpacked/name,app/name)
    fixtures=ROOT/'tests/fixtures/production-desktop'
    for file in fixtures.iterdir():
        if file.suffix in {'.exe','.dll'} or file.name=='WebView2-LICENSE.txt':shutil.copy2(file,app/file.name)
    python=app/'runtime';extract(runtime,python);dlls=python/'DLLs';dlls.mkdir()
    for file in list(python.iterdir()):
        if file.suffix=='.pyd' or (file.suffix=='.dll' and file.name not in {'python3.dll','python314.dll','vcruntime140.dll','vcruntime140_1.dll'}):shutil.move(file,dlls/file.name)
    shutil.copy2(fixtures/'python314._pth',python/'python314._pth')
    if bootstrapper is None:
        bootstrapper=out/'MicrosoftEdgeWebView2Setup.exe'
        if not bootstrapper.exists():urllib.request.urlretrieve(WEBVIEW_URL,bootstrapper)
    if bootstrapper.read_bytes()[:2]!=b'MZ':raise ValueError('Expected the official Microsoft WebView2 bootstrapper')
    if os.name=='nt':
        environment={**os.environ,'PRODUCTION_WEBVIEW_BOOTSTRAPPER':str(bootstrapper)}
        subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',"$s=Get-AuthenticodeSignature -LiteralPath $env:PRODUCTION_WEBVIEW_BOOTSTRAPPER; if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)') { throw 'Microsoft WebView2 publisher signature is not valid' }"],env=environment,check=True)
    shutil.copy2(bootstrapper,payload/'MicrosoftEdgeWebView2Setup.exe')
    shutil.copy2(ROOT/'scripts/install_production_payload.ps1',payload/'Install-Production.ps1')
    readme='''BACKWOODS PRODUCTION 1.0.0 - WINDOWS INSTALLER

Run Backwoods-Production-Setup-1.0.0.exe using the same Windows account as before.
Close Production first. Setup installs the original desktop launcher and the
bundled Python runtime. If Microsoft WebView2 Runtime is missing, its signed
Microsoft setup downloads the runtime; an internet connection is then required.

Default application: %LOCALAPPDATA%\\Backwoods Production\\Application
Production records: %LOCALAPPDATA%\\Backwoods Production\\Data\\backwoods.db

Your current Production screens, forms and workflow are retained. Existing
desktop records are not replaced. Application files are backed up before an
upgrade. An older source/portable database in the selected installation is
copied safely only when no desktop database exists; the original is retained.
Uninstall removes the installed program files and leaves records, application
backups and unrelated files in place. Do not uninstall to perform an upgrade.

Open Backwoods Production from the desktop or Start menu. The original manager
setup/sign-in remains available. One-time connections can be set up separately
with CONNECT-EXISTING-APPS.cmd in the installed Application folder. Installing
Production does not enable other app updates or change a live company.
'''
    (app/'INSTALL-README.txt').write_text(readme)
    files=sorted(p for p in payload.rglob('*') if p.is_file())
    if any(p.suffix in {'.db','.sqlite','.sqlite3'} for p in files):raise ValueError('No customer database may enter an installer')
    manifest={p.relative_to(payload).as_posix():sha(p) for p in files}
    (payload/'PAYLOAD-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    installed=sorted(p for p in app.rglob('*') if p.is_file())
    (out/'INSTALLED-FILE-MANIFEST.json').write_text(json.dumps({p.relative_to(app).as_posix():sha(p) for p in installed},indent=2)+'\n')
    (out/'INSTALL-README.txt').write_text(readme)
    provenance={'version':VERSION,'sourceCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'originalLauncherSha256':sha(fixtures/'Backwoods Production.exe'),'pythonSha256':PYTHON_SHA,'webViewBootstrapperSha256':sha(bootstrapper),'updateSha256':sha(update)}
    (out/'BUILD-PROVENANCE.json').write_text(json.dumps(provenance,indent=2)+'\n')
    output=out/f'Backwoods-Production-Setup-{VERSION}.exe'
    deletes='\n'.join(' Delete "$INSTDIR\\'+q(p.relative_to(app).as_posix().replace('/','\\'))+'"' for p in installed)
    directories=sorted((p for p in app.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True)
    removes='\n'.join(' RMDir "$INSTDIR\\'+q(p.relative_to(app).as_posix().replace('/','\\'))+'"' for p in directories)
    script=f'''
Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
Name "Backwoods Production"
OutFile "{q(output)}"
InstallDir "$LOCALAPPDATA\\Backwoods Production\\Application"
InstallDirRegKey HKCU "Software\\BackwoodsProduction" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show
Var ProductionMutex
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "Install Backwoods Production {VERSION}. Close Production before continuing. Your existing screens, production records and batch history are retained. Use the same Windows account as before."
!define MUI_FINISHPAGE_RUN "$INSTDIR\\Backwoods Production.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open Backwoods Production"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
VIProductVersion "{VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "Backwoods Production"
VIAddVersionKey /LANG=1033 "CompanyName" "Backwoods Brew"
VIAddVersionKey /LANG=1033 "FileDescription" "Backwoods Production Setup"
VIAddVersionKey /LANG=1033 "FileVersion" "{VERSION}"
VIAddVersionKey /LANG=1033 "ProductVersion" "{VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Backwoods Brew"

!macro GuardProduction Prefix
Function ${{Prefix}}GuardProduction
 retryClose:
 System::Call 'kernel32::CreateMutexW(p 0, i 1, w "Local\\BackwoodsProduction.Desktop") p .r0 ?e'
 Pop $1
 StrCmp $0 0 unavailable
 StrCmp $1 183 locked acquired
 locked:
 System::Call 'kernel32::CloseHandle(p r0)'
 IfSilent unavailable
 MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "Close Backwoods Production, including its notification icon, then click Retry. Your records have not been changed." IDRETRY retryClose
 unavailable:
 SetErrorLevel 10
 Quit
 acquired:
 StrCpy $ProductionMutex $0
FunctionEnd
Function ${{Prefix}}ReleaseProduction
 StrCmp $ProductionMutex "" done
 System::Call 'kernel32::ReleaseMutex(p $ProductionMutex)'
 System::Call 'kernel32::CloseHandle(p $ProductionMutex)'
 StrCpy $ProductionMutex ""
 done:
FunctionEnd
!macroend
!insertmacro GuardProduction ""
!insertmacro GuardProduction "un."
Function .onInit
 ${{IfNot}} ${{RunningX64}}
  MessageBox MB_OK "Backwoods Production requires 64-bit Windows."
  SetErrorLevel 11
  Quit
 ${{EndIf}}
 Call GuardProduction
FunctionEnd
Function .onGUIEnd
 Call ReleaseProduction
FunctionEnd
Function un.onInit
 Call un.GuardProduction
FunctionEnd
Function un.onGUIEnd
 Call un.ReleaseProduction
FunctionEnd

Section "Backwoods Production"
 SetShellVarContext current
 InitPluginsDir
 SetOutPath "$PLUGINSDIR\\production-payload"
 File /r "{q(payload)}/*"
 nsExec::ExecToStack '"$SYSDIR\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\\production-payload\\Install-Production.ps1" -TargetDirectory "$INSTDIR"'
 Pop $0
 Pop $1
 StrCmp $0 "0" installed
 FileOpen $2 "$TEMP\\Backwoods-Production-Setup-error.txt" w
 FileWrite $2 "$1"
 FileClose $2
 IfSilent failed
 MessageBox MB_OK|MB_ICONSTOP "Production could not be installed.$\\r$\\n$\\r$\\n$1"
 failed:
 Call ReleaseProduction
 SetErrorLevel 12
 Quit
 installed:
 SetOutPath "$INSTDIR"
 WriteUninstaller "$INSTDIR\\Uninstall.exe"
 CreateDirectory "$SMPROGRAMS\\Backwoods Production"
 CreateShortcut "$DESKTOP\\Backwoods Production.lnk" "$INSTDIR\\Backwoods Production.exe"
 CreateShortcut "$SMPROGRAMS\\Backwoods Production\\Backwoods Production.lnk" "$INSTDIR\\Backwoods Production.exe"
 WriteRegStr HKCU "Software\\BackwoodsProduction" "InstallDir" "$INSTDIR"
 WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsProduction" "DisplayName" "Backwoods Production"
 WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsProduction" "DisplayVersion" "{VERSION}"
 WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsProduction" "Publisher" "Backwoods Brew"
 WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsProduction" "InstallLocation" "$INSTDIR"
 WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsProduction" "UninstallString" '$\\"$INSTDIR\\Uninstall.exe$\\"'
 WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsProduction" "QuietUninstallString" '$\\"$INSTDIR\\Uninstall.exe$\\" /S'
 WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsProduction" "NoModify" 1
 WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsProduction" "NoRepair" 1
 Call ReleaseProduction
SectionEnd

Section "Uninstall"
 SetShellVarContext current
{deletes}
 Delete "$INSTDIR\\production-installation.json"
 Delete "$INSTDIR\\Uninstall.exe"
{removes}
 RMDir "$INSTDIR"
 Delete "$DESKTOP\\Backwoods Production.lnk"
 Delete "$SMPROGRAMS\\Backwoods Production\\Backwoods Production.lnk"
 RMDir "$SMPROGRAMS\\Backwoods Production"
 DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BackwoodsProduction"
 DeleteRegKey HKCU "Software\\BackwoodsProduction"
 Call un.ReleaseProduction
SectionEnd
'''
    nsi=out/'production-installer.nsi';nsi.write_text(script,encoding='utf-8')
    environment=dict(os.environ)
    if (nsis.parent.parent/'Include').is_dir():environment['NSISDIR']=str(nsis.parent.parent)
    subprocess.run([str(nsis),'-V2',str(nsi)],env=environment,check=True)
    output.with_suffix('.exe.sha256').write_text(sha(output)+'  '+output.name+'\n')
    print(json.dumps({'installer':str(output),'bytes':output.stat().st_size,'sha256':sha(output)}))
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--nsis',required=True,type=Path);parser.add_argument('--update',type=Path,default=ROOT/'dist/production/Backwoods-Production-Connected-Update.zip');parser.add_argument('--runtime',type=Path);parser.add_argument('--bootstrapper',type=Path);parser.add_argument('--out',type=Path)
    args=parser.parse_args();build(args.nsis.resolve(),args.update.resolve(),args.runtime,args.bootstrapper,args.out)
