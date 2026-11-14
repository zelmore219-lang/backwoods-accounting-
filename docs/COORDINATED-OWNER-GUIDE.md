# Backwoods coordinated apps and payroll: owner guide

Target packages: Main 8.2.10; Vendor 4.1.9; Business Accounting 1.0.8;
Employee Windows 0.4.6. Check the release/run status before calling these installed.
The existing Driver release and Employee Android release are retained.

## Install and connect

1. **Owner, Windows:** back up the existing Employee and Accounting databases,
   save work, and install updates over the existing programs using the same
   Windows account. Keep existing app profiles; do not uninstall/reset data.
   Install Employee first, then Vendor, Accounting and Main. Android Main,
   Vendor and Accounting use their existing package identities and signing key.
2. **Owner, Employee:** choose **Owner service → Connect or manage owner
   service…**. Use the existing connected Firebase project and **Start service**.
   Keep that owner Windows PC awake and connected. A previously connected PC
   needs no new Firebase project, billing plan, collection, service account or
   Firestore rules deployment. The service publishes its version and the private
   approved-payroll view inside its existing protected namespace.
3. **Owner, Employee → People → View** the actual person. Reuse their existing
   shared Backwoods login/verified UID. If necessary, use **Connected Backwoods
   accounts → Link employee record** after checking the exact person and UID.
   Do not link a timecard by a similar name. The previously reported
   jboozer/jcopeland shift has not been reassigned to zstyles.
4. **Owner:** finish the actual job assignment, business division, work location,
   effective date and compensation. For Vendor, assign a real **wholesale** job.
   Under **Application access → Assign access**, select **wholesale** and the
   actual job role. For finance staff, separately assign **accounting** with
   **accountant** (preparation/review), **owner** (approvals/configuration), or
   **viewer** (general financial reports, no payroll access). A Wholesale
   `driver` role does not grant the separate Driver application.
5. **Employee/owner/HR:** finish paper onboarding as described below, change any
   temporary password and complete required verified training. The owner can
   then select **Activate employee**. Activation still enforces the server's
   document, training and account checks. Payroll enrollment is not required.
6. **Owner, Accounting:** retain the company's existing **Sign in with
   Firebase** connection. Open **Payroll Management → Connect Employee**, review
   the actual workspace and companies, then select the actual legal company and confirm the connection. This reads
   the private Employee owner's finance view; it does not create another
   personnel database or reset Firebase. Review any reported missing/stale
   timesheet or identity issue before preparing pay.
7. **Existing finance accounts:** if a local account and Employee account are
   the same actual person, use **Settings & audit → Link existing financial
   account to Employee**, confirm both exact records/UID, and retain the financial
   record ID. Matching names are never linked automatically. New staff use their
   Employee username/password; password changes remain in Employee. Existing
   unlinked company recovery accounts and the verified company-owner sign-in
   remain available. Staff never receive the company owner's Firebase token.

## Paper onboarding without uploads

1. **Owner:** **People → View → Prepare paper onboarding packet**. Enter the
   actual restricted paper storage location, review the packet and select
   **Approve and assign paper packet**. The approval date uses the company
   timezone automatically. W-4, Alabama A-4, I-9, handbook acknowledgment and
   emergency contact assignments are created. Unfinished starter handbook/
   emergency drafts are replaced; signed versions are preserved on retries.
2. **Employee:** complete the actual paper originals, sign into Employee and use
   **My workspace → View → Acknowledge paper completion → Sign acknowledgment**
   for each required document. No file upload is needed.
3. **Authorized owner/HR, different from signer:** **Documents → Review →
   Approve document**, confirming the real paper record and storage reference.
   Complete the actual I-9 examiner, document examination and retention fields;
   an in-app acknowledgment does not replace that examination.
4. **Owner/employee:** finish shared login/password, required training and its
   authorized verification, then **Activate employee**. The dialog lists each
   incomplete requirement, the responsible person and the screen to use.

## Clock, review and approve

- **Employee, Vendor:** sign in with the same Backwoods username/password and
  choose **Clock In / Clock Out**. In **Vendor time clock**, select the actual
  assigned Wholesale job and choose **Clock In**, then **Clock Out** at shift
  end. Confirm the Employee service acknowledgment and displayed shift history.
  An open shift follows the UID across devices and connected clocks.
- Interrupted actions remain on the original device with their request ID.
  **Retry saved clock action** and the online retry reuse that ID. A delayed
  action requires office review; a device time is never silently substituted for
  a verified official time. Keep that device until the pending action is
  confirmed. Signing out does not delete its pending request.
- **Owner/manager, Employee → Time & attendance → Shared time cards → Refresh**:
  check source, actual person/UID, department, job, work location, original times
  and breaks. Use **Review** to approve/deny or make an audited correction.
  Corrections need review/approval before payroll. Main/Driver/Vendor/Employee
  original clock records remain preserved. Never approve your own timesheet.
- **Employee:** submit a complete ended workweek's timesheet. **Manager/owner:**
  resolve pending clock/correction issues, verify the actual overtime rule and
  approve the submitted timesheet. Approving an individual shared card alone
  does not approve the timesheet. PTO requires a separate reviewed request/job
  and paid hours; it does not count as worked overtime.
- **Owner, Hours & pay:** calculate hours and estimated gross by department.
  Open/disputed time is flagged. **Download approved time & PTO** remains
  available as the existing manual Accounting import option. Do not enter it
  again manually when automatic synchronization already imported those IDs.

## Prepare and approve payroll in Accounting

1. **Owner:** **Payroll Management → Configure payroll workflow**. Choose the
   current **HR.my** external workflow, or ADP/another actual provider. Save the
   workflow. Use **Map provider employee IDs** for actual provider IDs and earning
   codes when needed. A provider-format CSV requires its verified exact headers
   and specification; no ADP/HR.my API or certified import format is presumed.
2. **Owner/payroll staff:** **Sync approved Employee hours**. Review roster,
   source compensation and any withheld periods. The background connection
   also refreshes configured inputs. Only complete current approved timesheets
   and reviewed paid leave are eligible; importing inputs posts no wages.
3. **Prepare payroll:** select company, period, exclusive end date, pay date
   and provider. **Approved Employee timecards** uses Employee's actual reviewed
   regular/OT allocations. Add authorized bonuses, commissions, reimbursements,
   deductions or a provider-reviewed adjusted overtime rate where required.
   Alternatively select **Manual payroll** and enter reviewed regular/OT hours,
   actual wage rates or a salary amount for this payroll period, and additions.
   Manual entries do not modify attendance. Another active batch for an
   overlapping employee/period is blocked: open that existing batch instead.
4. **Salary:** automatic salary needs Employee's actual verified exemption and
   matching pay frequency. The salary is paid once for the selected complete
   period, with no second salary payment for PTO or additional hourly overtime
   for a verified exempt arrangement. Nonexempt, partial-period, mixed or
   multiple salary arrangements need qualified manual/provider review; the app
   does not invent proration or legal classification.
5. Select **Calculate preview**, check each employee/department and gross total,
   then **Create payroll draft → Review payroll**. Verify workweek overtime,
   bonus/commission effects, deductions and salary classification, and record a
   review explanation. **Owner:** **Approve gross payroll**. Approval records
   gross wage expense/accrual by department, without a bank/net-pay entry.
6. **Download CSV review** or **Download Excel review**. The Excel workbook
   includes payroll lines, department totals and control data. Downloads and
   retries retain the approved snapshot; a later rate change does not reprice it.
   **Record payroll rate override** records an effective-dated financial override;
   update the actual personnel job in Employee too when the underlying wage
   changes. In-period rate changes require reviewed split/manual preparation.

## What happens in HR.my / another external provider

- **Owner/payroll staff, outside Backwoods:** use the existing actual HR.my
  employer/employee records. Complete that service's required employee payroll
  and payment/tax configuration there. Keep protected tax forms and banking
  information in the established secure workflow, not a Backwoods CSV upload.
- Enter or import the reviewed wages, regular/OT hours, bonuses, commissions,
  reimbursements and authorized deductions using the provider's actual
  supported workflow. The general Backwoods CSV/Excel is a review worksheet;
  it is not advertised as a certified HR.my or ADP import.
- Review the final provider calculations. Arrange actual payments, withholding,
  deposits and filings through the provider/services that you really use.
  Backwoods makes no promise about HR.my's country-specific compliance or
  payment capabilities and does not send money or file returns.
- Save the actual provider receipt and final payroll report. Backwoods requires
  an actual confirmation reference before calling a batch received.

## Record actual results and payments in Accounting

1. **Owner:** open the approved batch → **Record provider receipt** after the
   provider confirms receipt. Enter its actual reference/evidence. Downloading
   a file never sets this status.
2. **Record final provider report**. Use **Download final-result CSV template**
   and fill actual dollar amounts from the final report, or enter those amounts
   in the form. Preserve exact batch/entry/employee/department fields. Enter
   actual gross, employee taxes, deductions, net payment including reimbursement,
   employer taxes/benefits and fees, including true zeros. Confirm departmental
   allocation and explain variances. **Post actual final report** reverses the
   estimate through an audit entry and posts actual expenses/liabilities once.
3. **Record actual bank settlement** only after payment actually occurred. Link
   an exact existing Bank credit line whenever it is already in the ledger;
   otherwise record a payment not previously entered. A documented existing
   unreconciled expense can be reclassified without a second bank credit.
   Complex or already reconciled expense allocations require Finance review.
4. Match the real statement using **Bank reconciliation**. Return to the batch
   and choose **Check bank reconciliation**. It becomes reconciled only when
   all actual liabilities are settled and all linked bank lines are reconciled.
   Exact report, receipt, export and payment retries do not create duplicates.

## What is still unavailable

- The unshipped Production prototype/source is missing. Manufacturing batches,
  finished-goods transfers to Vendor, manufacturing valuation/COGS and Production
  shared login cannot be implemented or verified without it. Existing stock
  writers have not been changed to invent this connection.
- No new provider API credentials, sandbox or verified provider import schema
  were supplied. No live payroll submission/payment/filing was performed.
- No employee records, approvals, actual timecards or live Firebase settings
  were changed as part of testing. Your real identity links, reviews, verified
  rules, provider setup and payroll approvals must be completed by you.
- Android packages are build/signature checked, with browser phone/tablet flows;
  no physical Android device, physical printer or real bank acceptance is claimed.
