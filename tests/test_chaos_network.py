import pytest
from unittest.mock import MagicMock, patch
from requests.exceptions import Timeout, ConnectionError, HTTPError
from src.api.network import fetch_address_balance
from src.config.config import CONFIG

class TestNetworkChaos:

    @classmethod
    def setup_class(cls):
        """
        Setup fake configuration needed by network functions.
        This prevents KeyError when the code tries to access CONFIG['performance'].
        """
        CONFIG['performance'] = {
            "retry_attempts": 3,
            "timeout": 5,
            "backoff_factor": 0.1
        }
        # Ensure API profile defaults exist
        CONFIG['api'] = {
            "active_profile": "Default",
            "profiles": {
                "Default": {
                    "base_url": "https://api.kaspa.org",
                    "endpoints": {
                        "balance": "/addresses/{kaspaAddress}/balance"
                    }
                }
            }
        }

    # Simulate a complete network timeout
    @patch("src.api.network._session.get")
    def test_network_timeout_handling(self, mock_get):
        mock_get.side_effect = Timeout("Simulated Timeout")
        
        # The function should catch the error, log it, and return None
        # It should NOT crash the app.
        result = fetch_address_balance("kaspa:test")
        assert result is None

    # Simulate a 500 Server Error from Kaspa API
    @patch("src.api.network._session.get")
    def test_server_error_handling(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = HTTPError("500 Server Error")
        mock_get.return_value = mock_resp
        
        result = fetch_address_balance("kaspa:test")
        assert result is None

    # Simulate receiving malformed JSON (Garbage Data)
    @patch("src.api.network._session.get")
    def test_malformed_json_handling(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Return valid JSON but missing the 'balance' key entirely
        mock_resp.json.return_value = {"wrong_key": "123"} 
        mock_get.return_value = mock_resp
        
        result = fetch_address_balance("kaspa:test")
        # Should handle missing key gracefully
        assert result is None 
