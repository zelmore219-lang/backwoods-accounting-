# One ledger on Windows and Android

## Ready to configure

The Business Accounting APK is a native Android client for the existing accounting web app. It signs in to Firebase, discovers the company HTTPS service, opens that service's ledger, offers native printing / Save as PDF, supports file picking, and asks before saving downloaded records. TLS validation remains enabled; HTTP and other-origin navigation inside the company WebView are blocked. Changing the connection clears this phone's web login/cache, preserving server records.

**No accounting service has been deployed.** Users no longer enter its address: the service publishes its origin into the bound owner's private Firebase discovery document, which the APK reads after sign-in. Existing Windows data is not automatically uploaded. This APK does not create a second phone ledger.

## Shared service setup

An administrator must configure a host with persistent storage, backups and trusted HTTPS. To retain the current local feed route, run the service on the same Windows computer and user as both connected source apps. That computer must stay on and reachable for mobile access. A separate cloud host also needs an authenticated source-feed integration. An ephemeral SQLite file on Cloud Run is not a durable deployment.

Stop the desktop accounting app, back up its data and create/verify its owner locally **before** exposing the service. Keep the same `%LOCALAPPDATA%\BackwoodsBusinessAccounting` directory. Only one accounting service should own it.

With Python 3.12+ and this complete source folder, run:

```powershell
py -3 run.py --no-browser --port 8765 --public-origin https://books.YOUR-DOMAIN.com
```

Use your actual company domain. The backend remains bound to loopback. `--public-origin` recognizes only that proxy's Host/Origin and sets Secure cookies for it; it does not configure DNS, certificates, a firewall, hosting or Firebase.

A separately installed Caddy reverse proxy on that computer can use:

```caddyfile
books.YOUR-DOMAIN.com {
    header Strict-Transport-Security "max-age=31536000"
    reverse_proxy 127.0.0.1:8765
}
```

This requires domain ownership, working DNS and the normal certificate-validation ports. Keep backend port 8765 private. Verify the real HTTPS certificate and login on another device, then verify the service has published its private Firebase discovery document. Sign in to the APK with the linked Firebase owner; it discovers the origin automatically. Use the native **Print** toolbar button for printing/PDF; physical printers require an Android print service. These deployment steps have not been executed against a real domain here.

To use the same shared ledger on Windows, open that company origin in a browser. The updated desktop source also supports `BACKWOODS_ACCOUNTING_SERVER_URL`: set it to the HTTPS origin before launching a **rebuilt** desktop app. That mode opens the shared service without starting another local ledger. Older installed builds do not gain this feature automatically.

```powershell
$env:BACKWOODS_ACCOUNTING_SERVER_URL = 'https://books.YOUR-DOMAIN.com'
# Launch the rebuilt Business Accounting executable from this shell.
```

Moving hosts requires deliberate database/feed migration and verified backups. Windows DPAPI payroll tokens must be reconnected after moving to another Windows user/computer. Do not commit business records or service-account credentials to GitHub.

## Firebase integration

Automatic source upload, immutable chunk validation, the background importer and Firebase-bound accounting login are implemented. See [the one-time setup](../firebase/SETUP.md) for the exact Firebase paths and deployment steps. The sender runs while a source owner app is open; it is not a trigger watching all staff writes server-side. Phone OS background suspension can delay sending.

No live rules, hosting or source control-total reconciliation have been deployed/tested. Fixture tests and signed APKs do not establish production operation. The current project's public Firebase configuration grants no administrative access.
