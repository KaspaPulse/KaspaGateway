import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
from src.gui.transaction_manager import _process_raw_transactions

# Simplified strategy: limit list size and complexity to speed up generation
transaction_strategy = st.dictionaries(
    keys=st.text(min_size=1, max_size=10),  # Shorter keys
    values=st.one_of(
        st.text(max_size=20), 
        st.integers(), 
        st.floats(), 
        st.none(), 
        st.booleans()
    ),
    min_size=1,
    max_size=10 # Limit dictionary size
)

class TestDeepFuzzing:

    # Suppress slow data generation warning and limit list size
    @settings(
        max_examples=50, 
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
        deadline=None
    )
    @given(st.lists(transaction_strategy, max_size=20)) # Limit list length
    def test_process_transactions_stability(self, raw_txs):
        """
        Property-Based Test:
        Feeds garbage/random data into _process_raw_transactions.
        The test PASSES if the function handles it gracefully (returns empty DF or processes it)
        without raising an unhandled exception (Crash).
        """
        target_address = "kaspa:qrandomaddress"
        prices = {"usd": 0.15}
        
        try:
            # The function should either return a DataFrame or handle internal errors.
            # It should NOT raise a ValueError/KeyError up to the UI.
            df = _process_raw_transactions(raw_txs, target_address, prices)
            
            # If we get a dataframe, it must have columns if it's not empty
            if not df.empty:
                assert "txid" in df.columns
                assert "amount" in df.columns
                
        except Exception as e:
            # If an exception leaks out, we fail the test unless it's a specific known safe error
            pytest.fail(f"Crash detected with fuzz input: {e}")
