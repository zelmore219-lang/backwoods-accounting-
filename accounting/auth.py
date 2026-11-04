"""Local user accounts and hashed, expiring sessions. No default credentials."""
import hashlib
import json
import os
import secrets
import time
import unicodedata
import uuid
from .ledger import AccountingError,now

SCHEMA='''
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts(username TEXT PRIMARY KEY,failures INTEGER NOT NULL,locked_until INTEGER NOT NULL,last_at INTEGER NOT NULL);
'''


def username(value):
    value=unicodedata.normalize('NFKC',str(value)).strip().casefold()
    if not value or len(value)>100:raise AccountingError('Enter a username or email up to 100 characters')
    return value


def password_hash(password,salt):
    return hashlib.scrypt(str(password).encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1,dklen=64,maxmem=64*1024*1024).hex()


def validate_password(password):
    if not isinstance(password,str) or len(password)<12 or len(password)>256:
        raise AccountingError('Use a password or passphrase between 12 and 256 characters')


def create_user(ledger,value,first=False):
    if first and ledger.db.execute('SELECT 1 FROM users').fetchone():raise AccountingError('Owner setup is already complete; sign in')
    user=username(value.get('username',''));password=value.get('password');validate_password(password)
    role='owner' if first else value.get('role','viewer')
    if role not in {'owner','accountant','viewer'}:raise AccountingError('Unknown user role')
    name=str(value.get('name') or user).strip()[:100]
    salt=secrets.token_hex(16);uid=str(uuid.uuid4())
    with ledger.db:
        ledger.db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)',(uid,user,name,role,password_hash(password,salt),salt,now()))
        ledger.audit('user-created',{'id':uid,'username':user,'role':role})
    return {'id':uid,'username':user,'name':name,'role':role}


def login(ledger,value):
    user=username(value.get('username',''));password=str(value.get('password',''))[:256]
    attempt=ledger.db.execute('SELECT * FROM login_attempts WHERE username=?',(user,)).fetchone()
    current=int(time.time())
    if attempt and attempt['locked_until']>current:raise AccountingError('Too many failed attempts. Try again after the 15-minute lockout.')
    r=ledger.db.execute('SELECT * FROM users WHERE username=?',(user,)).fetchone()
    expected=r['password_hash'] if r else '0'*128
    actual=password_hash(password,r['salt'] if r else '0'*32)
    if not r or not secrets.compare_digest(expected,actual):
        failures=(attempt['failures'] if attempt and current-attempt['last_at']<900 else 0)+1
        with ledger.db:
            ledger.db.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?,?)',(user,failures,current+900 if failures>=5 else 0,current))
        raise AccountingError('Username or password is incorrect')
    token=secrets.token_urlsafe(32)
    with ledger.db:
        ledger.db.execute('DELETE FROM login_attempts WHERE username=?',(user,))
        ledger.db.execute('DELETE FROM sessions WHERE expires_at<?',(current,))
        ledger.db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),r['id'],current+8*3600))
        ledger.audit('login',{'username':user})
    return token,{k:r[k] for k in ['id','username','name','role']}


def session_user(ledger,token):
    if not token:return None
    r=ledger.db.execute('SELECT u.id,u.username,u.name,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
    return dict(r) if r else None


def logout(ledger,token):
    with ledger.db:ledger.db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))


def change_password(ledger,user,value):
    r=ledger.db.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
    if not secrets.compare_digest(r['password_hash'],password_hash(str(value.get('currentPassword','')),r['salt'])):raise AccountingError('Current password is incorrect')
    new=value.get('newPassword');validate_password(new);salt=secrets.token_hex(16)
    with ledger.db:
        ledger.db.execute('UPDATE users SET salt=?,password_hash=? WHERE id=?',(salt,password_hash(new,salt),user['id']))
        ledger.db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
        ledger.audit('password-changed',{'username':user['username']})
