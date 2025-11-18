import os
import pytest
from src.database.db_locker import acquire_lock, _get_lock_path, _get_wal_path
from src.config.config import CONFIG

TEST_DB_NAME = "CrashTest.duckdb"
CONFIG['paths'] = {'database': './test_data'}

class TestCrashRecovery:

    def setup_method(self):
        if not os.path.exists('./test_data'):
            os.makedirs('./test_data')
        
    def test_stale_lock_cleanup(self):
        lock_path = os.path.join('./test_data', f"{TEST_DB_NAME}.lock")
        wal_path = os.path.join('./test_data', f"{TEST_DB_NAME}.wal")

        # 1. Simulate previous crash (create lock file with dead/fake PID)
        fake_dead_pid = 99999999 
        with open(lock_path, 'w') as f:
            f.write(str(fake_dead_pid))
        
        # 2. Simulate stuck WAL file (Write Ahead Log)
        # Reference: src/database/db_locker.py
        with open(wal_path, 'w') as f:
            f.write("dummy wal data")

        assert os.path.exists(lock_path)
        assert os.path.exists(wal_path)

        # 3. Attempt to run app (acquire_lock)
        # Code should detect dead PID, delete stale files, and succeed
        # Reference: src/database/db_locker.py (function _cleanup_stale_lock)
        result = acquire_lock(TEST_DB_NAME)
        
        assert result is True, "Failed to recover from stale lock"
        
        # 4. Ensure stale WAL file is deleted to avoid corruption
        # Reference: src/database/db_locker.py
        assert not os.path.exists(wal_path), "Stale WAL file was NOT cleaned up!"
        
        print("Recovery test passed: Stale locks and WAL files cleaned.")
