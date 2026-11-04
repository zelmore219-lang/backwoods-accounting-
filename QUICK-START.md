# Start using Backwoods Business Accounting

1. Install `Backwoods-Business-Accounting-Setup-1.0.0.exe` on a **64-bit Windows** computer. Test under a separate Windows user first. The installer includes its runtime; you do not need Python installed separately. It is unsigned, so Windows may identify it as an unknown publisher.
2. Open **Backwoods Business Accounting** and create your owner login. There is no default password. Save your passphrase securely.
3. In **Settings**, enter your legal company name, business address and phone for printed records. Download a backup after setup and keep backups off this computer.
4. In **App connections**, use the connected source-app package to enable the Brew and Vendor Ordering feeds on this same Windows user account. Back up the original apps first. Their accounting remains separate, and they send copies into one company ledger here.
5. Choose the main-app ledger connection before importing plain main-app backups. Switching those formats in populated books is deliberately blocked to prevent duplicate postings.
6. Review the first import against the totals in each source app. Resolve historical inventory-cost warnings. Do not enter the same sale, bill or payroll twice.
7. Use **New transaction** for business invoices, bills and expenses not recorded by the source apps. Use **Company ledger → Journal entry** for opening balances, transfers and correcting entries.
8. Use **Production costs**, **Retail & wholesale pricing**, **Inventory planning**, and **Equipment & depreciation** to manage business costs and registered assets. Planning estimates do not silently change your books or source-app prices.
9. Use **Payroll & employees** to connect an approved Gusto Embedded Payroll company. Complete provider, employer, state, employee and bank onboarding before live payroll. Test the connection in demo first. Provider credentials are entered securely in the Windows app, not in chat. Merely installing this app does not activate direct deposit or tax filing.
10. In **Tax updates & liabilities**, select the states where you actually operate. Official-source changes will be queued for review while the app runs. The connected provider supplies maintained payroll tax calculations.
11. Use **Print Center** or a record's print link to print or save PDFs. Provider payroll has links for the provider's official employee pay stubs once connected and authorized.
12. Reconcile actual bank statements before closing accounting periods. A payroll submission, an accounting entry, and a settled bank payment are different events.

Closing the desktop window keeps it in the system tray when available. Choose **Exit** from that tray to stop the app. The local database is kept in `%LOCALAPPDATA%\BackwoodsBusinessAccounting` and is preserved when uninstalling.

Read `VALIDATION.md` for tested behavior and the remaining Windows/live-service checks. Test company data and payroll credentials are not bundled in the installer.
