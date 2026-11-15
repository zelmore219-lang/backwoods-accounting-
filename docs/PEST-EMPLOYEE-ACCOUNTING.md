# Connect Pest Control to Employee and Business Accounting

Windows release set: Pest Control **0.10.0**, Employee Employer **0.4.9**, Business Accounting **1.0.11**. Use your existing legal company and a separate **Pest Control** department. Production is deferred.

## 1. Install the Windows updates — owner

Save work and make your normal backups. Let pending Pest work synchronize first. Fully quit Pest, including **Quit Backwoods and stop alerts** in its tray menu, before installing. In Employee’s tray menu select **Quit and stop owner service**. Close Accounting before installing its update.

Download and run these installers under the same Windows account that holds your existing data:

* [Pest Control Setup 0.10.0](https://github.com/zelmore219-lang/backwoods-brew-releases/releases/download/pest-0.10.0/Backwoods-Pest-Control-Setup-0.10.0.exe)
* [Employee Setup 0.4.9](https://github.com/zelmore219-lang/backwoods-brew-releases/releases/download/employees-0.4.9/Backwoods-Employees-Setup-0.4.9.exe)
* [Business Accounting 1.0.11 downloads](https://github.com/zelmore219-lang/backwoods-accounting-/releases/tag/apps-pest-integration-2026-11-15)

Install over the existing apps. Open Pest from the installed Start-menu shortcut. **Help → About Backwoods** should show **0.10.0**. Its new **App updates → Check for updates…** menu opens the update wizard. An old portable EXE will still open the old version; use the installed shortcut. Keep old devices/data until pending work has synchronized.

## 2. Start the existing Employee service — owner, on the owner Windows PC

Open Employee Employer. Use **Owner service → Connect or manage owner service…**. Start the existing shared service and wait for **Owner service is online**. Keep this PC awake, online, and running the service while people connect or synchronize.

If the service was never connected, the dialog uses **Open Google owner sign-in → Complete connection → Load owner records → Start shared Employee service**. Sign out of the local draft session and sign in with your existing Main Backwoods username/password after connecting. Existing drafts remain in the same database.

This update adds no Firebase project, paid plan, or extra rules deployment. Pest retains `bugzapper-3397f`; Employee retains the existing Backwoods project. Do not copy one project's settings over the other. If Pest 0.9 was never commissioned, complete its existing [Firebase setup](https://github.com/zelmore219-lang/backwoods-brew-window-original1/blob/codex/pest-employee-accounting/firebase/SETUP.md): publish the current private Pest Realtime Database rules and enable Email/Password in its existing project. Preserve the configured Pest owner UID. Those live settings were not changed or verified during this release.

## 3. Prepare each existing employee — owner / HR

In Employee, open **People → the employee**. Use the existing record and shared Backwoods identity.

* **Job assignments → Assign job**: select the actual **Pest Control** position/location and enter the actual pay arrangement, rate, and effective date. The update supplies a Pest Control division, location, and technician position under the existing `backwoods` company. It does not assign a job or pay rate to anyone. For another configured company, use its actual organizational records.
* **Application access → Assign access**: select **pest**, then the appropriate **technician** or **manager** role. Confirm the grant becomes **active**. This grants Employee-side access; it does not create or replace a Pest login.
* If the shared identity is missing, use **Create shared login** or link the verified existing account through **Connected Backwoods accounts**. Never create another employee just to retry a connection.

Pest's owner uses **Accounts** to check that the person's existing Pest staff account is active. Customer accounts cannot link as employees or send billing. Confirm the exact person and both accounts before linking.

## 4. Finish onboarding for new hires — employee, then owner / HR

An existing activated employee keeps their status. A new hire must still satisfy every item in **Onboarding progress** before **Activate employee** succeeds.

1. Owner: **People → employee → Prepare paper onboarding packet**. Enter where completed paper forms are kept, review the five-form checklist, then **Approve and assign paper packet**. The packet approval date uses today's date in the organization's time zone. Previous signatures and actual form dates are retained.
2. Employee: complete/sign the paper **W-4, Alabama A-4, I-9, Employee handbook acknowledgment, and Emergency contact form**. Return the originals to owner / HR. In Employee, open each assigned document, choose **Acknowledge paper completion**, enter your full name, check the declarations, and **Sign acknowledgment**. No document upload is needed for this paper workflow.
3. Owner / HR: review each actual signed original, use its document review action, and record its secure paper-file reference. Complete the separate I-9 examination fields using the actual dates/procedure. An employee acknowledgment alone does not approve an I-9 or replace employer review.
4. Employee completes assigned training; owner / HR uses **Verify training completion** after checking evidence. Employee completes the required password/account setup.
5. Owner opens **Activate employee**, resolves every listed incomplete requirement, checks the review confirmation, and selects **Activate employee**. Confirm status is **active**. The server checks the current records again.

Payroll setup is not an activation requirement. No Gusto login or Gusto employee mapping is needed.

## 5. Link the two verified accounts — each Pest staff member

Sign in to Pest with your existing Pest username/password. Open **Employee & Accounting**.

1. Enter your existing Employee username/password and select **Connect Employee**.
2. Review both displayed usernames and UIDs. Confirm they are both yours.
3. Check **I verified these existing Pest and Employee accounts belong to me**, then **Link verified accounts**.
4. Confirm **Verified Employee account linked.** Retrying this operation retains one link. If an account is already linked to someone else, the server stops rather than guessing or reassigning it.

## 6. Record and approve Pest time — employee, then a different authorized reviewer

In Pest **Employee & Accounting → Pest time clock**, select the actual **Pest Control job** and use **Clock In / Clock Out**. A missing job is fixed in Employee **Job assignments**, not by inventing a location or rate.

Offline punches stay on the original device with their original timestamps and request identifiers. Once online, select **Retry saved clock actions**. Keep that device's data until it reports zero retained actions. Offline/delayed time requires office review. These punches retain device-captured timestamps as evidence, while the official card starts with server receipt times. Confirm the actual work times with the employee and use **Review → Action: Correct and return to pending review → Save review** before approving/finalizing payroll. The corrected clock fields are explicitly UTC: convert the confirmed local times for the actual date, then complete the separate approval; a brief retry interval must not be treated as the full offline shift.

Owner / authorized manager: Employee **Time & attendance → Shared time cards → Refresh**. Find the Pest source and Pest Control job/location. Review actual punches, breaks and any requested correction, then approve or deny. Use audited corrections when necessary; keep original timestamps. A different authorized person reviews the employee's time; self-approval is blocked.

Approved timesheets, departmental hours, estimated pay and PTO remain in Employee. Review and freeze the appropriate timesheet before using its payroll inputs. Estimates are not a completed payroll payment.

## 7. Authorize Pest billing for the existing company — owner

Sign in to Pest as its existing owner. Open **Employee & Accounting**, then **Connect Employee** using the Employee organization-owner account. The owner can authorize billing without linking a personal clock account.

In **Business Accounting connection**, select the existing legal company, check the company-review confirmation, and select **Sync billing to Accounting**. This sends issued/voided invoices and actual recorded payments through the private Employee finance connection. Service notes, addresses, gate codes, photos, signatures and personnel forms are excluded.

## 8. Confirm the import in Accounting — Accounting owner

1. If not connected already, open **Payroll Management → Connect Employee** and connect the same Employee workspace and actual legal company.
2. Open **App connections → Connect Pest Control**.
3. Review the displayed company, Pest project and invoice count. Check the confirmation and select **Connect and import**.
4. Confirm the Pest Control panel says **Connected to this legal company · department Pest Control** and shows a last accepted snapshot.
5. Open **Company ledger → Trace source → Pest Control**. Compare the source invoices, payments, receivables and dates with Pest. Repeating the sync/import does not post duplicate records.

Pest service revenue uses account **4030**, receivables **1100** and applicable recorded sales tax **2100**. Recorded cash uses **1010**; checks and external card/ACH receipts use **1030 Undeposited Funds** until you record the actual settlement/reconciliation. The connection does not infer a bank deposit, chemical cost or payroll payment.

Keep the connected Pest owner app, Employee owner service and Accounting open and online for subsequent synchronization. A missing source record, changed company mapping or invalid billing snapshot stops import for review. Unpaid voids reverse once; closed/reconciled history still requires the established correction workflow.

## 9. Payroll and final live confirmation — owner / payroll staff

Employee handles onboarding, time tracking, review/denial, PTO, departmental hours and estimated pay. Accounting receives approved Employee payroll inputs through **Payroll Management**. Continue actual payroll processing with your HR.my workflow and record/reconcile actual results in Accounting; this update does not connect to HR.my or send payroll automatically.

Before live use, confirm one real employee's existing identities, actual Pest job/rate and onboarding status; then review a real shift through Employee and verify a real issued invoice/payment in the correct company books. Release tests used fictitious records and emulator projects, not your live business data.

This release provides Pest's Windows connection. Existing Pest Android 0.9.0 is retained; it does not gain the new connection screen from this Windows update. Employee and Driver Android signing/upgrade work remains separate. No new Android package or physical-device acceptance for those apps is claimed here.
