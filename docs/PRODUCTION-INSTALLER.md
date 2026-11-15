# Backwoods Production for Windows

Run **Backwoods-Production-Setup-1.0.0.exe** using the Windows account that owns your existing Production records. Close Production first, including its notification icon. Setup creates the desktop and Start menu shortcuts and an entry in Windows Installed apps.

The installer includes the original desktop launcher, Python 3.14 runtime, application and connection libraries. There is no Python installation or ZIP assembly step. If Microsoft WebView2 Runtime is missing, the included Microsoft-signed bootstrapper installs it; that step needs an internet connection.

The existing layout, navigation, recipes, batch work, packaging and release forms stay in place. Installing Production does not configure company connections, publish other apps or activate their update feeds. The original manager setup and standalone sign-in remain available until the company connection is configured separately.

The default installation is `%LOCALAPPDATA%\Backwoods Production\Application`. The original launcher keeps desktop records in `%LOCALAPPDATA%\Backwoods Production\Data\backwoods.db`. Upgrades preserve the existing desktop database, retain the original screen shell assets and save the old application files in a dated backup beside Application. An existing desktop database takes precedence over a source/portable database. If only one older database exists in the selected application folder, SQLite's backup API copies its committed data, including WAL records, into the desktop data directory and retains the original.

Run Setup again to upgrade or reinstall. Setup refuses to replace the application while Production is running. Uninstall removes the installed program files, shortcuts and registration; it retains production records, backups and unrelated files. Keep normal independent backups of business records.

Native Windows acceptance covers fresh installation, the normal original desktop launch, WebView rendering, old unmanaged installation upgrade, reinstallation, original screen assets, database preservation, the running-app guard, invalid payload rejection, uninstall data retention and source-database migration with committed WAL records. See the release's `INSTALLER-ACCEPTANCE.json`, `BUILD-PROVENANCE.json` and SHA-256 file for the exact accepted build.
