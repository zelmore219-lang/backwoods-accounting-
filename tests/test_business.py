import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from urllib.error import URLError

from accounting.ledger import AccountingError,Ledger
from accounting.business import register_asset,asset_state,depreciate,dispose_asset,payroll_preview,post_payroll,pay_payroll
from accounting import auth,tax_watch
from accounting.payroll_provider import Gusto,ProviderError,review_payroll,submit_payroll,sync_payrolls,accounting_document,STATES
from accounting.printing import render
from accounting.locking import RunLock


COMPANY='11111111-1111-4111-8111-111111111111'
PAYROLL='22222222-2222-4222-8222-222222222222'


def provider_payroll():
    return {'payroll_uuid':PAYROLL,'version':'version-1','check_date':'2026-10-15','processed':False,'pay_period':{'start_date':'2026-10-01','end_date':'2026-10-15'},'totals':{
        'gross_pay':'1000.00','net_pay':'750.00','employee_taxes':'200.00','employer_taxes':'100.00','employee_benefits_deductions':'50.00','company_debit':'1100.00','reimbursements':'0.00'}}


class BusinessTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.temp.name)/'books.db')
    def tearDown(self):self.ledger.close();self.temp.cleanup()
    def asset(self,**overrides):
        v={'name':'Bottling machine','cost':1200,'salvage':120,'lifeMonths':12,'purchaseDate':'2025-01-01','startMonth':'2025-01','postPurchase':True,'fundingAccount':'1020'};v.update(overrides)
        register_asset(self.ledger,v);return asset_state(self.ledger)[-1]
    def test_straight_line_posts_once_and_stops_at_residual(self):
        a=self.asset();self.assertEqual(sum(r['amount'] for r in a['schedule']),108000)
        depreciate(self.ledger,{'id':a['id'],'throughMonth':'2025-12'})
        a=asset_state(self.ledger)[0];self.assertEqual(a['bookValue'],12000)
        with self.assertRaises(AccountingError):depreciate(self.ledger,{'id':a['id'],'throughMonth':'2025-12'})
        r=self.ledger.report();self.assertEqual(r['expense'],108000);self.assertEqual(r['balanceDifference'],0)
    def test_depreciation_remainder_allocates_every_cent(self):
        a=self.asset(cost='100.01',salvage=0,lifeMonths=3)
        self.assertEqual([r['amount'] for r in a['schedule']],[3334,3334,3333])
    def test_disposal_removes_cost_accumulation_and_recognizes_gain(self):
        a=self.asset();depreciate(self.ledger,{'id':a['id'],'throughMonth':'2025-12'})
        dispose_asset(self.ledger,{'id':a['id'],'date':'2026-01-01','proceeds':200})
        r=self.ledger.report();balances={a['code']:a['balance'] for a in r['trial']}
        self.assertEqual(balances['1500'],0);self.assertEqual(balances['1590'],0);self.assertEqual(balances['4800'],-8000)
        self.assertEqual(r['balanceDifference'],0)
        with self.assertRaises(AccountingError):depreciate(self.ledger,{'id':a['id'],'throughMonth':'2026-01'})
    def test_future_depreciation_is_rejected(self):
        a=self.asset(purchaseDate='2090-01-01',startMonth='2090-01')
        with self.assertRaises(AccountingError):depreciate(self.ledger,{'id':a['id'],'throughMonth':'2090-01'})
        self.assertEqual(self.ledger.report()['expense'],0)
    def test_asset_register_rejects_double_linked_cost(self):
        a=self.asset();v={'name':'Duplicate machine','cost':1200,'salvage':0,'lifeMonths':12,'purchaseDate':'2025-01-01','startMonth':'2025-01','postPurchase':False,'linkedSource':'manual','linkedId':a['linkedId']}
        with self.assertRaises(AccountingError):register_asset(self.ledger,v)
    def test_payroll_accrual_and_payment_after_closed_period(self):
        with self.ledger.db:self.ledger.db.execute('INSERT INTO employees VALUES(?,?,?,?)',('e1','Pat','{}','2026-01-01'))
        value={'employeeId':'e1','periodStart':'2026-10-01','periodEnd':'2026-10-15','date':'2026-10-15','gross':1000,'federal':100,'state':20,'socialSecurity':62,'medicare':14.5,'deductions':3.5,'employerSocialSecurity':62,'employerMedicare':14.5,'employerUnemployment':6,'paid':False}
        result=payroll_preview(value);self.assertEqual(result['net'],80000);self.assertEqual(result['employerTaxes'],8250)
        post_payroll(self.ledger,value);self.ledger.set_settings({'closed_through':'2026-10-31'})
        d=self.ledger.db.execute("SELECT source_id FROM documents WHERE kind='payroll'").fetchone()[0]
        pay_payroll(self.ledger,{'id':d,'date':'2026-11-01'})
        self.assertEqual(next(a for a in self.ledger.report()['trial'] if a['code']=='2200')['balance'],0)
        with self.assertRaises(AccountingError):pay_payroll(self.ledger,{'id':d,'date':'2026-11-02'})
    def test_overlapping_employee_payroll_is_rejected(self):
        with self.ledger.db:self.ledger.db.execute('INSERT INTO employees VALUES(?,?,?,?)',('e1','Pat','{}','2026-01-01'))
        v={'employeeId':'e1','periodStart':'2026-10-01','periodEnd':'2026-10-15','date':'2026-10-15','gross':100}
        post_payroll(self.ledger,v)
        with self.assertRaises(AccountingError):post_payroll(self.ledger,{**v,'periodStart':'2026-10-10','periodEnd':'2026-10-20'})
    def test_operating_states_has_all_50_plus_dc(self):
        self.assertEqual(len(STATES),51);self.assertEqual(set(STATES),set(tax_watch.SOURCES)-{'US'})
    def test_tax_monitor_only_queues_source_changes(self):
        def fetch1(url,headers):return ('<html><h1>Official payroll guidance</h1><p>'+('Initial guidance. '*12)+'</p></html>').encode(),{}
        def fetch2(url,headers):return ('<html><h1>Official payroll guidance</h1><p>'+('New guidance for review. '*12)+'</p></html>').encode(),{}
        tax_watch.configure(self.ledger,{'states':['AL','CA']})
        tax_watch.check_source(self.ledger,'AL',fetch1)
        self.assertEqual(self.ledger.db.execute('SELECT COUNT(*) FROM tax_changes').fetchone()[0],0)
        tax_watch.check_source(self.ledger,'AL',fetch2)
        change=self.ledger.db.execute('SELECT * FROM tax_changes').fetchone()
        self.assertEqual(change['status'],'needs-review');self.assertEqual(self.ledger.rows(),[])
        tax_watch.review_change(self.ledger,{'id':change['id'],'status':'reviewed','review':'Confirmed provider handling; no local formula change','effectiveDate':'2027-01-01'})
        self.assertEqual(self.ledger.rows(),[])
    def test_unavailable_tax_source_remains_visible(self):
        def failure(url,headers):raise URLError('Unavailable test source')
        result=tax_watch.check_source(self.ledger,'AL',failure);self.assertFalse(result['ok'])
        self.assertTrue(self.ledger.db.execute('SELECT error FROM tax_sources').fetchone()[0])
    def test_print_templates_escape_business_values(self):
        self.ledger.set_settings({'company':'<script>not executable</script>'})
        text=render(self.ledger,{'type':'profit-loss'},{'role':'owner'})
        self.assertIn('&lt;script&gt;',text);self.assertNotIn('<script>not executable</script>',text)
        for kind in ['ledger','balance-sheet','trial-balance','assets','payroll','inventory','tax-liabilities']:
            self.assertIn('<table>',render(self.ledger,{'type':kind},{'role':'owner'}))
    def test_exclusive_lock_prevents_overlapping_restore(self):
        lock=RunLock(Path(self.temp.name))
        try:
            with self.assertRaises(AccountingError):RunLock(Path(self.temp.name))
        finally:lock.close()


class AuthTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.temp.name)/'auth.db')
    def tearDown(self):self.ledger.close();self.temp.cleanup()
    def test_no_default_account_and_password_is_hashed(self):
        self.assertIsNone(self.ledger.db.execute('SELECT 1 FROM users').fetchone())
        user=auth.create_user(self.ledger,{'username':'OWNER','password':'a long test passphrase'},first=True)
        row=self.ledger.db.execute('SELECT * FROM users').fetchone();self.assertNotEqual(row['password_hash'],'a long test passphrase')
        token,logged=auth.login(self.ledger,{'username':'owner','password':'a long test passphrase'})
        self.assertEqual(logged['id'],user['id']);self.assertEqual(auth.session_user(self.ledger,token)['role'],'owner')
        auth.logout(self.ledger,token);self.assertIsNone(auth.session_user(self.ledger,token))
    def test_password_change_invalidates_existing_sessions(self):
        auth.create_user(self.ledger,{'username':'owner','password':'old test passphrase'},first=True)
        token,user=auth.login(self.ledger,{'username':'owner','password':'old test passphrase'})
        auth.change_password(self.ledger,user,{'currentPassword':'old test passphrase','newPassword':'new test passphrase'})
        self.assertIsNone(auth.session_user(self.ledger,token))
    def test_repeated_bad_passwords_lock_login(self):
        auth.create_user(self.ledger,{'username':'owner','password':'correct long test passphrase'},first=True)
        for i in range(5):
            with self.assertRaises(AccountingError):auth.login(self.ledger,{'username':'owner','password':'bad'})
        with self.assertRaisesRegex(AccountingError,'lockout'):auth.login(self.ledger,{'username':'owner','password':'correct long test passphrase'})


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.ledger=Ledger(Path(self.temp.name)/'provider.db');self.payroll=provider_payroll();self.calls=[];self.fail_submit=False
        def transport(method,path,body,headers):
            self.calls.append((method,path,body))
            if path.endswith('/submit'):
                if self.fail_submit:raise AccountingError('Uncertain test timeout')
                return {'accepted':True}
            if '/payrolls?' in path:return [self.payroll]
            return copy.deepcopy(self.payroll)
        self.client=Gusto(self.temp.name,{'accessToken':'unit-test-token-not-a-credential','companyId':COMPANY,'environment':'production'},transport)
    def tearDown(self):self.ledger.close();self.temp.cleanup()
    def test_review_required_before_submit(self):
        with self.assertRaises(AccountingError):submit_payroll(self.ledger,self.client,PAYROLL,'invalid','RUN PAYROLL 2026-10-15')
        self.assertFalse(any('/submit' in c[1] for c in self.calls))
    def test_changed_calculation_cannot_be_submitted(self):
        r=review_payroll(self.ledger,self.client,PAYROLL);self.payroll['version']='changed'
        with self.assertRaises(AccountingError):submit_payroll(self.ledger,self.client,PAYROLL,r['fingerprint'],'RUN PAYROLL 2026-10-15')
    def test_explicit_submission_is_not_duplicate_or_paid(self):
        r=review_payroll(self.ledger,self.client,PAYROLL)
        result=submit_payroll(self.ledger,self.client,PAYROLL,r['fingerprint'],'RUN PAYROLL 2026-10-15')
        self.assertEqual(result['status'],'submitted');self.assertEqual(self.ledger.rows(),[])
        with self.assertRaises(AccountingError):submit_payroll(self.ledger,self.client,PAYROLL,r['fingerprint'],'RUN PAYROLL 2026-10-15')
        self.assertEqual(sum('/submit' in c[1] for c in self.calls),1)
    def test_uncertain_submission_is_retained_and_not_retried(self):
        r=review_payroll(self.ledger,self.client,PAYROLL);self.fail_submit=True
        with self.assertRaises(AccountingError):submit_payroll(self.ledger,self.client,PAYROLL,r['fingerprint'],'RUN PAYROLL 2026-10-15')
        self.assertEqual(self.ledger.db.execute('SELECT status FROM provider_actions').fetchone()[0],'unknown')
        with self.assertRaises(AccountingError):submit_payroll(self.ledger,self.client,PAYROLL,r['fingerprint'],'RUN PAYROLL 2026-10-15')
        self.assertEqual(sum('/submit' in c[1] for c in self.calls),1)
    def test_definitive_rejection_requires_new_review_before_retry(self):
        r=review_payroll(self.ledger,self.client,PAYROLL)
        original=self.client.submit
        def rejected(pid):raise ProviderError('Provider validation blocker',definitive=True,status=422)
        self.client.submit=rejected
        with self.assertRaises(ProviderError):submit_payroll(self.ledger,self.client,PAYROLL,r['fingerprint'],'RUN PAYROLL 2026-10-15')
        self.assertEqual(self.ledger.db.execute('SELECT status FROM provider_actions').fetchone()[0],'rejected')
        self.client.submit=original
        with self.assertRaises(AccountingError):submit_payroll(self.ledger,self.client,PAYROLL,r['fingerprint'],'RUN PAYROLL 2026-10-15')
        r=review_payroll(self.ledger,self.client,PAYROLL)
        self.assertEqual(submit_payroll(self.ledger,self.client,PAYROLL,r['fingerprint'],'RUN PAYROLL 2026-10-15')['status'],'submitted')
    def test_processed_payroll_accrues_once_without_claiming_bank_settlement(self):
        self.payroll['processed']=True
        sync_payrolls(self.ledger,self.client);sync_payrolls(self.ledger,self.client)
        balances={r['code']:r['balance'] for r in self.ledger.report()['trial']}
        self.assertEqual(balances['5200'],100000);self.assertEqual(balances['5210'],10000)
        self.assertEqual(balances['2250'],-75000);self.assertEqual(balances['2160'],-30000)
        self.assertNotIn('1020',balances)
        self.assertEqual(self.ledger.report()['balanceDifference'],0)
    def test_demo_payroll_never_changes_company_books(self):
        self.payroll['processed']=True;self.client.environment='demo'
        result=sync_payrolls(self.ledger,self.client);self.assertTrue(result['demo']);self.assertEqual(self.ledger.rows(),[])
    def test_tips_and_reimbursements_reconcile(self):
        p=provider_payroll();p['processed']=True;p['totals'].update(employee_cash_tips='100',employee_paycheck_tips='50',net_pay='650',reimbursements='20')
        doc=accounting_document(p,COMPANY);self.ledger.import_documents('provider',[doc],{})
        balances={r['code']:r['balance'] for r in self.ledger.report()['trial']}
        self.assertEqual(balances['5200'],85000);self.assertEqual(balances['2260'],5000);self.assertEqual(balances['2250'],-67000)
        self.assertEqual(self.ledger.report()['balanceDifference'],0)
    def test_unreconciled_totals_do_not_get_forced_to_balance(self):
        p=provider_payroll();p['processed']=True;p['totals']['net_pay']='999'
        with self.assertRaises(AccountingError):accounting_document(p,COMPANY)


if __name__=='__main__':unittest.main()
