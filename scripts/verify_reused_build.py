"""Reuse native bytes only when all shipped application sources are identical."""
import re,subprocess,sys
base=sys.argv[1]
if not re.fullmatch('[a-f0-9]{40}',base):raise SystemExit('Use an exact staged build SHA')
changed=subprocess.check_output(['git','diff','--name-only',base,'HEAD','--'],text=True).splitlines()
ci={'scripts/source_installed.cjs','scripts/employee_time_installed.cjs','scripts/payroll_management_smoke.py','scripts/verify_reused_build.py'}
blocked=[name for name in changed if name not in ci and not name.startswith(('.github/workflows/','tests/','docs/'))]
if blocked:raise SystemExit('Build new packages after shipped source changes: '+', '.join(blocked))
print('Verified unchanged shipped sources against '+base+'; changes are confined to tests, CI or documentation.')
