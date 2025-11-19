import os
import pytest
import time
from src.database.db_locker import acquire_lock, release_lock, _get_lock_path
from src.config.config import CONFIG

# Setup dummy path for testing
TEST_DB_NAME = "Test_Transactions.duckdb"
CONFIG['paths'] = {'database': './test_data'} 

class TestDatabaseLocking:

    def setup_method(self):
        if not os.path.exists('./test_data'):
            os.makedirs('./test_data')

    def teardown_method(self):
        # Cleanup after test
        release_lock(TEST_DB_NAME)
        lock_file = os.path.join('./test_data', f"{TEST_DB_NAME}.lock")
        if os.path.exists(lock_file):
            os.remove(lock_file)

    # Test Scenario: Running two instances simultaneously
    # Reference: src/database/db_locker.py
    def test_double_locking_prevention(self):
        # 1. First attempt to acquire lock (should succeed)
        first_attempt = acquire_lock(TEST_DB_NAME)
        assert first_attempt is True, "First instance failed to acquire lock"
        
        # Verify lock file existence
        lock_path = _get_lock_path(TEST_DB_NAME)
        assert os.path.exists(lock_path)

        # 2. Second attempt to acquire lock (should fail)
        second_attempt = acquire_lock(TEST_DB_NAME)
        assert second_attempt is False, "Second instance acquired lock illegally!"
        
        print("Concurrency test passed: Second instance blocked.")
