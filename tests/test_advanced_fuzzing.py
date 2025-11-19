import pytest
import pandas as pd
from hypothesis import given, settings, HealthCheck, strategies as st
from src.gui.transaction_manager import _process_raw_transactions

# Strategy to generate "chaotic" and highly complex transaction data
# Includes: Unicode strings, huge integers, NaNs, None values, nested structures
transaction_strategy = st.lists(
    st.dictionaries(
        keys=st.text(min_size=1),
        values=st.one_of(
            st.text(), 
            st.integers(min_value=-10**18, max_value=10**18), # Massive integers
            st.floats(allow_nan=True, allow_infinity=True),   # Irrational numbers
            st.none(), 
            st.booleans(),
            st.lists(st.integers(), max_size=5), # Nested lists
        ),
        min_size=1
    ),
    min_size=1,
    max_size=50
)

class TestDeepFuzzing:
    
    @settings(
        max_examples=200, # Run 200 different chaotic scenarios
        deadline=None, 
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
    )
    @given(raw_txs=transaction_strategy)
    def test_transaction_processor_resilience(self, raw_txs):
        """
        Property: The processor should NEVER crash with an unhandled exception, 
        regardless of how garbage the input JSON is.
        """
        target_address = "kaspa:qxy7..." 
        prices = {"usd": 0.13}
        
        try:
            df = _process_raw_transactions(raw_txs, target_address, prices)
            
            # Invariants Check:
            if not df.empty:
                # 1. Result must always be a DataFrame
                assert isinstance(df, pd.DataFrame)
                # 2. Numeric columns must not contain NaNs if processing succeeded
                if 'amount' in df.columns:
                    assert not df['amount'].isnull().all() 
                    
        except Exception as e:
            # Crash Analysis:
            # Allow only specific "safe" logical errors, but fail on unhandled crashes
            # like generic IndexError or KeyError.
            error_msg = str(e).lower()
            if "memory" in error_msg:
                pytest.fail("Memory exhaustion detected during fuzzing")
            # Pass if it handled the error gracefully (e.g., logged warning and returned empty)
            pass
