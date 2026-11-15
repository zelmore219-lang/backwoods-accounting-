"""Fictional device fixture; this file is in the test APK only."""
import json,threading
from pathlib import Path
from accounting import server,auth,payroll_management as pm
server.ROOT=Path(program_dir)
fixture_app=server.Application(Path(fixture_dir))
ledger=fixture_app.ledger()
auth.create_user(ledger,{'username':'native.owner','password':'fictional-android-passphrase','name':'Fictional Android Owner'},first=True)
token,user=auth.login(ledger,{'username':'native.owner','password':'fictional-android-passphrase'})
feed={'schemaVersion':1,'type':'backwoods-employee-payroll-feed','project':'fixture-only','companies':[{'id':'backwoods','name':'Fictional Backwoods'}],
 'employees':[{'id':'fixture-staff','firebase_uid':'fixture-uid','username':'fictional.employee','name':'Fictional Employee','employee_number':'FIX-1','company_id':'backwoods','status':'active',
 'jobs':[{'id':'fixture-job','division_id':'wholesale','division_name':'Wholesale','location_id':'fixture-location','location_name':'Fictional warehouse','title':'Packer','pay_type':'hourly','rate_cents':1500,'effective_date':'2020-01-01','timezone':'America/Chicago'}]}],
 'approvedPackets':[],'issues':[],'revision':'native-fixture'}
pm.sync_employees(ledger,'fictional-native-workspace',feed,confirm=True)
pm.save_provider(ledger,{'id':'hrmy','name':'HR.my external workflow'})
batch=pm.create_batch(ledger,{'requestKey':'native-fixture-payroll','companyId':'backwoods','method':'manual','periodStart':'2026-10-19','periodEndExclusive':'2026-10-26','payDate':'2026-10-30','providerId':'hrmy','entries':[{'employeeId':'fixture-staff','assignmentId':'fixture-job','payType':'hourly','rateCents':1500,'regularMinutes':2400,'overtimeMinutes':300,'overtimeRateCents':2250,'bonusCents':5000}]})
pm.review_batch(ledger,{'id':batch['id'],'reviewed':True,'overtimeReviewed':True,'reason':'Fictional native acceptance review'})
pm.approve_batch(ledger,{'id':batch['id'],'confirmed':True})
assert batch['payload']['entries'][0]['calculation']['grossCents']==76250
ledger.close()
fixture_server=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);fixture_server.application=fixture_app
threading.Thread(target=fixture_server.serve_forever,daemon=True).start()
result=json.dumps({'port':fixture_server.server_port,'session':token,'batch':batch['id']})
