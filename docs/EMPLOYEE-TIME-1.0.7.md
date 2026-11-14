# Approved Employee time and PTO in Business Accounting 1.0.7

In Employee Employer 0.4.5, use Hours & pay → Download approved time & PTO for a
company and a period containing complete approved timesheets. Extract the ZIP.
It contains business-accounting-time.json, department totals, approved worked
hours / estimated gross wages, reviewed paid time off and supporting timecards.

In Business Accounting, open Connect apps. Under Import Employee hours or an
older backup, choose Source app → Employee Employer app, select
business-accounting-time.json, then Preview import. Confirm the company, period,
record count and review messages, then Import into company ledger. In Payroll &
employees, Approved Employee hours & PTO shows the approved employee work,
departments and paid time off. Process payroll here using the actual payroll
workflow and HR.my results. The Employee app does not connect a payroll provider,
file taxes or pay anyone.

Importing approved hours creates supporting records only. It does not post a
payroll expense, liability, payment or tax estimate. Stable original timesheet
and time-off IDs prevent duplicate records on repeat imports. Conflicting
overlapping timesheets or another company's Employee records are rejected.
Existing Main/Vendor imports and financial postings stay in place. Authorized
owner/accounting users can review the records; read-only viewers cannot open or
print private employee pay data.

This source starts from the exact current app-feed source commit
eaed598a242a16a2b775ef009cbc0598177fefe5. Version 1.0.7 updates Accounting; Main
8.2.9 and Vendor 4.1.8 remain independent. Windows packaging and install/reinstall
checks run separately before release. The companion Employee browser test has
already exercised an actual approved ZIP, this import screen, a duplicate retry,
department pay display and PTO without financial posting or live company data.
