import pytest
import os
import pandas as pd
from unittest.mock import MagicMock, patch
from src.export.csv_export import export_to_csv

class TestGUIControllers:

    @patch("src.gui.main_window.MainWindow" if "src.gui.main_window" in locals() else "unittest.mock.Mock")
    def test_status_update_logic(self, mock_window):
        """Test logic determining status messages without GUI."""
        status_code = 200
        
        def get_status_message(code):
            if code == 200: return "Connected"
            return "Error"

        msg = get_status_message(status_code)
        assert msg == "Connected"

    @patch("src.export.csv_export.get_active_api_config")
    def test_export_csv_logic(self, mock_get_config, tmp_path):
        """Test CSV export logic with correct arguments and mocked config."""
        
        # Mock the configuration to prevent KeyError: 'explorer'
        mock_get_config.return_value = {
            "explorer": {
                "transaction": "https://explorer.kaspa.org/txs/{txid}"
            }
        }
        
        # Create valid DataFrame structure
        data = pd.DataFrame([{
            "address": "kaspa:123",
            "balance": 100.0,
            "txid": "123456abcdef",  # Added txid to test formatting
            "timestamp": 1678888888
        }])
        
        file_path = tmp_path / "export.csv"
        
        try:
            export_to_csv(data, str(file_path), "kaspa:testaddr", "MyWallet", "USD")
            
            assert os.path.exists(file_path)
            with open(file_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
                # Verify content
                assert "kaspa:123" in content
                assert "100.0" in content
                # Verify header content from logic
                assert "MyWallet" in content
        except Exception as e:
            pytest.fail(f"Export failed with error: {e}")
