"""Cross-platform exclusive access for server lifetime and offline restores."""
from .ledger import AccountingError
import os


class RunLock:
    def __init__(self,directory):
        directory.mkdir(parents=True,exist_ok=True)
        self.file=open(directory/'accounting.lock','a+b')
        self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                if not self.file.read(1):self.file.write(b'0');self.file.flush()
                self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close();raise AccountingError('Business Accounting is already using this data folder. Close it before restoring or starting another copy.') from exc
    def close(self):
        if self.file.closed:return
        if os.name=='nt':
            import msvcrt
            self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
        self.file.close()
