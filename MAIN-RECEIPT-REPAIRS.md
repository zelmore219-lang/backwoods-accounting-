# Backwoods Brew Main 8.2.9 — navigation and receipt repairs

This repairs the existing Main app from `79c8ca8814efc8c96e12209534ebc0ead6025a50`, the latest connected Main 8.2.7 source/release branch found in the repository. Production work, the Employee app, Central Accounting, Vendor Ordering and Driver Delivery are outside this change.

## Changes

- Removed the two floating launchers shown in the supplied screenshot by unloading their embedded UI screens. Historical local wholesale data and all retained source files remain intact. The Firebase configuration, username sign-in, Main accounting feed and shared wholesale read adapter still load.
- Replaced receipt pop-ups with an in-app preview. Browser/tablet printing uses a rendered same-origin iframe; Windows uses the existing Electron bridge with an isolated print document and system printer selection. Android registers a native print plugin that opens the Android print service. Printing does not save, reverse or repeat a sale.
- Customer receipts now show the saved transaction ID, time, cashier, location, item quantities, unit/line amounts, subtotal, discount, tax, total and payment details. New sales retain a business/location snapshot for consistent reprints. Historic receipts use their recorded item amounts; missing historic cash information is labeled rather than invented.
- Updated checkout, receipt history and the older receipt/kitchen queue to the same print path. Receipt cancellation and print failures leave the completed transaction saved.

## Verified

- Six automated receipt/native-handler/core-integrity tests passed. Username authentication, inventory deductions, ledger generation and the application's synchronization function are byte-identical to the source baseline.
- Fifteen source/profile/connector regression tests and five Firebase feed tests passed, including complete/redacted snapshots, duplicate suppression, permissions and failed publication.
- Actual Main bundle tested in Chromium using an isolated test company and the existing local-login path. A real POS transaction saved, depleted recipe inventory, produced a complete receipt, and reprinted from receipt history. Pop-up creation was blocked during the test. The accounting export retained the order and balanced ledger; existing wholesale-storage bytes were preserved. Browser iframe printing and Windows-bridge cancellation were exercised. Desktop and narrow-screen previews were captured.
- Real Electron rendered a nonblank receipt PDF through its native print engine. Extracted PDF text includes the transaction and payment values. The native handler waits for rendering before calling system printing and handles cancellation.
- Windows installer built with Main 8.2.9 and its updated renderer/native print code.

Test evidence is generated under `test-results/main-receipts/`. Reproduce with:

```sh
node --test source-app-updates/main/tests/receipts.test.mjs
node source-app-updates/main/scripts/verify.cjs
node tests/source_updates.test.cjs
node tests/firebase_feed.test.cjs
python scripts/main_receipt_smoke.py
desktop/node_modules/electron/dist/electron --no-sandbox --disable-dev-shm-usage --disable-gpu --ozone-platform=headless scripts/main_native_receipt_smoke.cjs
```

## Installation and remaining verification

Close Main and back up its records before installing `Backwoods-Brew-Connected-Setup-8.2.9.exe`. The connected profile and existing Firebase project are preserved. Open a saved receipt, choose **Print / Save PDF**, select the installed printer and its paper size, and print a small test sale. No pop-up permissions are required.

The Main-only CI workflow builds an APK with the repository's retained signing identity. It does not generate a replacement key for an installed app, publish Firebase rules, change the global update feed, or build the other applications.

Physical Windows installation, receipt-printer hardware and Android/iPad print services still require checks on the target devices. Live Firebase sign-in and cross-device delivery were not exercised with customer credentials; the preserved integration code, actual exported packet and mocked transport were tested. The Employee app repairs and onboarding documents remain queued for a later app-specific task.
