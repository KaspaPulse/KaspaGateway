import pytest
from src.utils.validation import sanitize_cli_arg, validate_ip_port

class TestSecurity:
    
    # Test prevention of Command Injection
    # Reference: src/utils/validation.py
    def test_sanitize_cli_arg_injection(self):
        # Attempts to inject Shell commands
        malicious_inputs = [
            "127.0.0.1; rm -rf /",
            "127.0.0.1 && shutdown",
            "| echo 'hacked'",
            "> overwrite.txt",
            "$(whoami)"
        ]
        
        for input_str in malicious_inputs:
            cleaned = sanitize_cli_arg(input_str)
            # Ensure dangerous characters are removed
            assert ";" not in cleaned
            assert "&" not in cleaned
            assert "|" not in cleaned
            assert ">" not in cleaned
            assert "$" not in cleaned
            print(f"Tested: {input_str} -> Cleaned: {cleaned}")

    # Test prevention of Path Traversal attacks
    # Reference: src/utils/validation.py
    def test_path_traversal(self):
        risky_path = "../../windows/system32/cmd.exe"
        cleaned = sanitize_cli_arg(risky_path)
        assert ".." not in cleaned, "Failed to strip parent directory traversal"

    # Test precise IP/Port validation
    # Reference: src/utils/validation.py
    def test_ip_port_validation(self):
        valid = "127.0.0.1:16110"
        invalid_overflow = "127.0.0.1:99999" # Invalid port
        invalid_format = "127.0.0.1" # Missing port
        
        assert validate_ip_port(valid) is not None
        assert validate_ip_port(invalid_overflow) is None
        assert validate_ip_port(invalid_format) is None
