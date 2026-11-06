# Updating the Backwoods apps

Main, Vendor and Business Accounting now use one public update feed, with separate Windows and Android packages for each app:

`https://github.com/zelmore219-lang/backwoods-accounting-/releases/download/app-updates/backwoods-updates.json`

For Windows, install Main 8.2.6, Vendor 4.1.7 or Accounting 1.0.5 manually once. These versions fix Electron redirect handling; the earlier Windows updater builds cannot load GitHub release redirects correctly. Android versions Main 8.2.5, Vendor 4.1.6 and Accounting 1.0.4 can receive the newer APKs through their existing native update screen. The updater cannot add itself to an older installed app. Back up and close the Windows app before that first installation. Keep existing Android installations and data; do not uninstall to bypass a signing conflict.

## In the app

Open **App updates**. Windows Accounting also has **Help → App updates**. Android Accounting has an **Updates** button in its books toolbar and sign-in screen. Main and Vendor expose **App updates** only inside **Settings**; there is no floating or sign-in update button.

The wizard shows the current and latest versions, the update feed and download progress. Use **Check**, **Download**, then **Install**. **Enabled** controls background checks; **Auto-download** is optional and off by default. Windows checks at startup and every six hours while running. Android checks when the app opens, at most once every six hours. Background checks require Internet access. Installation always requires approval.

Windows opens the downloaded setup wizard and closes the app. Reopen it after setup. Company databases and profiles remain in their existing locations. Android opens its package installer. On Android 8+, allow this app to install updates when Android asks, then return and tap Install again. Existing app data is preserved by an Android update.

Checksums are verified before installation. Android also checks package name, version code, device compatibility and signing certificate. A mismatched signing key is blocked with instructions to keep the existing app and data. The retained test key matches the published Accounting 1.0.3 and Vendor 4.1.5 APKs. Earlier APKs, including Main 8.2.4, use another key and require that original signing identity for in-place upgrades. Windows packages remain unsigned test builds.

## One-time GitHub setup

The repository needs GitHub Actions enabled and this repository secret:

- `ANDROID_UPDATE_KEYSTORE_BASE64`: base64 encoding of the retained `.build-resources/android-signing/debug.keystore`. This is private key material; enter it only through GitHub repository secrets. Never attach it to a release, commit it, or paste it into chat.

The public certificate fingerprint is pinned in `android-apps/update-signing-certificate.txt`. Builds fail if their APK certificate differs. Do not generate a replacement key for an existing app. The checked-in debug alias/password are Android's standard test credentials; the private key itself remains outside Git.

If Codex configures GitHub for you, its fine-grained token needs **Actions**, **Contents**, **Secrets**, and **Workflows** with read/write access to this repository. Enter that token securely as `GITHUB_RELEASE_TOKEN` in environment settings. Apps do not contain GitHub credentials. Future workflow runs use GitHub's own short-lived `GITHUB_TOKEN` with repository Contents write permission.

The workflow file must be merged into the default branch before GitHub offers its Run workflow button. Environments which require approval for workflow runs must complete that approval in GitHub.

## Publish the next update

1. Push the tested code changes to the repository.
2. Open **Actions → App updates (Windows and Android) → Run workflow**.
3. Set newer numeric versions, such as Accounting `1.0.5`, Vendor `4.1.7`, and Main `8.2.6`. Use newer versions for all three when rebuilding all packages. Reusing a version with different bytes is rejected.
4. Leave **Publish packages and activate the update feed** enabled. To build for review without distributing an update, turn it off.
5. Run the workflow and wait for it to finish successfully. It builds all six packages, runs tests, verifies identities and checksums, publishes the versioned package release, then updates the public feed last.

Versioned package downloads are immutable. The `app-updates` release contains only the replaceable feed. An interrupted feed replacement can temporarily make checks unavailable; the updater reports the failure and keeps the installed app. A failed build never activates a new feed. Concurrent release workflows are serialized. Check the workflow logs if a build or upload fails; do not mark it successful manually.

The Windows icon and shared updater packaging hooks are included in standard installer builds. `scripts/prepare_updaters.py` refreshes generated Electron updater files for development. Android sources are shared directly under `android-apps/shared-updater`. `BUILD-APK-WINDOWS.cmd` requires the retained signing keystore at its documented ignored path.

## Validation limits

Local automated checks cover update-policy rejection, native IPC isolation, checksums, damaged downloads, installation approval, the browser wizard and Android policy rules. APK identities/signatures and packaged Windows resources are inspected. Windows setup execution, Android package installation and physical-device operation require device testing before production rollout. The current signing identity is for test releases; production signing needs a planned migration and key custody.

For a Main/Vendor-only release, keep Accounting’s version unchanged and enable **Keep the exact published Accounting packages** in the workflow. Its existing signed downloads are checksum-verified and reused byte-for-byte, so Accounting users are not offered an unrelated update.

If Main finds multiple legacy Windows profiles, its first-launch chooser lists their folder names and local-data modification dates. Choose the profile whose records you intend to copy, or cancel. The originals are not merged, changed or deleted. A successful choice is remembered by the connected-profile marker.

Android Main 8.2.7, Vendor 4.1.8 and Accounting 1.0.6 fix the installer handoff. The updater has a distinct FileProvider component, attaches the APK URI as ClipData with a temporary read grant, resumes after the per-app installation permission is granted, and shows verification/handoff failures in a dialog. If an older app downloads an update but cannot open its installer, open the matching release APK from a browser once and choose Update. Preserve the installed app and its data; do not uninstall. Shared Robolectric tests exercise the merged manifests, APK URI readability and isolation of private records in all three apps.
