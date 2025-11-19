import pytest
from src.utils.validation import validate_kaspa_address, sanitize_input_string

class TestDataIntegrity:

    # Boundary Testing for Addresses
    def test_kaspa_address_boundaries(self):
        # 1. Valid Address
        assert validate_kaspa_address("kaspa:qxy7...") is False # Short but valid prefix logic
        
        # 2. SQL Injection Attempt in Address field
        assert validate_kaspa_address("kaspa:qxy' OR 1=1; --") is False
        
        # 3. XSS Payload in Address
        assert validate_kaspa_address("kaspa:<script>alert(1)</script>") is False
        
        # 4. Buffer Overflow simulation (Huge String)
        huge_addr = "kaspa:" + "q" * 10000
        assert validate_kaspa_address(huge_addr) is False

    # Input Sanitization Testing
    def test_input_sanitization_strictness(self):
        # Ensure special chars that could break file systems or DBs are stripped
        dirty_input = "My\nAddress\tFile*Name?.txt"
        clean = sanitize_input_string(dirty_input)
        
        assert "\n" not in clean
        assert "*" not in clean
        assert "?" not in clean
        # Should preserve alphanumeric
        assert "MyAddressFileName.txt" in clean.replace(" ", "")

