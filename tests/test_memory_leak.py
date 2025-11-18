import pytest
import os
import psutil
import gc
import pandas as pd
from src.gui.transaction_manager import _process_raw_transactions

class TestMemoryStability:
    
    def test_dataframe_memory_cleanup(self):
        """
        Simulates processing massive data multiple times to ensure memory is released.
        """
        process = psutil.Process(os.getpid())
        
        # 1. Measure initial memory
        gc.collect()
        mem_start = process.memory_info().rss / 1024 / 1024 # MB
        
        # 2. Loop: Create heavy load -> Process -> Discard
        raw_txs = [{"transaction_id": f"tx_{i}", "inputs": [], "outputs": [], "is_accepted": True} for i in range(5000)]
        prices = {"usd": 1.0}
        
        for _ in range(10): # Run 10 cycles
            df = _process_raw_transactions(raw_txs, "kaspa:addr", prices)
            del df # Explicitly delete
            
        # 3. Force Garbage Collection
        gc.collect()
        
        # 4. Measure final memory
        mem_end = process.memory_info().rss / 1024 / 1024 # MB
        
        # 5. Check for significant leaks (allowing slight fluctuation overhead)
        # If memory grew by more than 20MB after cleanup, we have a leak.
        growth = mem_end - mem_start
        print(f"Memory Growth: {growth:.2f} MB")
        
        assert growth < 20.0, f"Potential Memory Leak Detected! Growth: {growth:.2f} MB"
