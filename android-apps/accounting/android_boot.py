"""Embedded full accounting engine. Firestore is the shared remote data store."""
import json
import os
from pathlib import Path
import threading
import time

_app=None
_server=None
_threads_started=False

def start(files_dir):
    global _app,_server
    if _server:return _server.server_port
    os.environ['BACKWOODS_ANDROID']='1'
    import certifi
    os.environ['SSL_CERT_FILE']=certifi.where()
    from accounting import server
    server.ROOT=Path(files_dir)/'accounting-program'
    _app=server.Application(Path(files_dir)/'business-accounting')
    # Other Android apps can reach loopback. Only this app's native WebView gets
    # the bootstrap secret via JNI; an HTTP visitor never receives it.
    _app.native_private_bootstrap=True
    _server=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    _server.application=_app
    threading.Thread(target=_server.serve_forever,daemon=True,name='local-accounting').start()
    return _server.server_port

def sign_in(email,password):
    from accounting.shared_runtime import company_sign_in
    result=company_sign_in(_app,str(email),str(password))
    _watch()
    return json.dumps({**result,'port':_server.server_port,'bootstrap':_app.cookie})

def _watch():
    global _threads_started
    if not _threads_started:
        from accounting import tax_watch
        threading.Thread(target=_app.watch_firebase,daemon=True,name='firebase-accounting').start()
        threading.Thread(target=tax_watch.monitor,args=(_app,),daemon=True,name='tax-source-watch').start()
        _threads_started=True

def local_books():
    from accounting.ledger import AccountingError
    ledger=_app.ledger()
    try:
        if not ledger.db.execute('SELECT 1 FROM users').fetchone():raise AccountingError('Sign in to Firebase and create the company owner account first.')
    finally:ledger.close()
    _app.shared.last_checked=time.monotonic()
    _watch()
    return json.dumps({'port':_server.server_port,'bootstrap':_app.cookie})
