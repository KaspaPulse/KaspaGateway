# src/utils/validation.py
"""
Provides validation, sanitization, and helper functions for user input
and other data.
"""

import re
import logging
from urllib.parse import urlparse
from src.utils.i18n import get_all_translations_for_key
from typing import Optional, Tuple, Any, Set

logger = logging.getLogger(__name__)

# This is loaded at runtime, so we initialize it here.
# It's used to prevent validating placeholder text as a real address.
_address_placeholders: Set[str] = get_all_translations_for_key("Enter Kaspa Address or Select from Dropdown")


def _sanitize_for_logging(log_message: Any) -> str:
    """
    Sanitizes a message for logging, removing newlines.
    Converts non-string inputs to string safely.
    """
    if not isinstance(log_message, str):
        try:
            log_message = str(log_message)
        except Exception:
            return "[Unloggable Content]"
    return log_message.replace('\n', ' ').replace('\r', ' ')


def validate_kaspa_address(address: str) -> bool:
    """
    Validates a Kaspa address string against the 'kaspa:' prefix and bech32m-like pattern.
    Also checks against known placeholder strings.
    """
    global _address_placeholders
    if not _address_placeholders:
        # Re-fetch if it was empty during module import
        _address_placeholders = get_all_translations_for_key("Enter Kaspa Address or Select from Dropdown")

    if not isinstance(address, str) or not address:
        return False

    address_lower = address.lower()

    if address in _address_placeholders:
        return False

    # Pattern for kaspa:bech32m
    pattern = r"^kaspa:[qpzry9x8gf2tvdw0s3jn54khce6mua7l]+$"
    is_valid = re.match(pattern, address_lower) is not None

    if not is_valid:
        if address not in _address_placeholders:
            logger.warning(f"Address validation FAILED for: {_sanitize_for_logging(address)}")

    return is_valid


def validate_url(url: str) -> bool:
    """Checks if a string is a valid URL with a scheme and network location."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except (ValueError, AttributeError):
        return False


def validate_ip_port(ip_port: str) -> Optional[Tuple[str, str]]:
    """
    Validates if a string is a valid [host_or_ip]:port combination.
    Returns (host, port) tuple if valid, else None.
    """
    if not ip_port:
        return None

    # Regex for optional host/IP (allowing hostnames with dots/dashes)
    # and mandatory port
    match = re.match(r"^([\w\.\-]*)?:(\d+)$", ip_port)
    if not match:
        return None

    ip_or_host = match.group(1) if match.group(1) else ""
    port = match.group(2)

    try:
        # Check for valid port range
        if not 1 <= int(port) <= 65535:
            return None
    except ValueError:
        return None

    return ip_or_host, port


def sanitize_input_string(input_str: str, max_length: int = 100) -> str:
    """
    Sanitizes a generic user input string (like an address name),
    allowing basic characters and enforcing a length limit.
    """
    if not isinstance(input_str, str):
        return ""
    # Whitelist alphanumeric, space, dash, underscore, parentheses
    sanitized = re.sub(r'[^a-zA-Z0-9 \-_()]', '', input_str)
    return sanitized.strip()[:max_length]


def sanitize_cli_arg(arg_str: str) -> str:
    """
    Sanitizes a string intended to be used as a value (not an option key)
    in a command-line argument.

    Blocks path traversal, quote characters, and argument injection prefixes
    like '-' or '/'. Allows file paths (including spaces) and IP:port combinations.
    """
    if not isinstance(arg_str, str):
        return ""

    # 1. Block path traversal
    if '..' in arg_str:
        logger.warning(f"Blocked potential path traversal: {_sanitize_for_logging(arg_str)}")
        return ""

    # 2. Remove simple quotes. Stricter sanitization will follow.
    sanitized = re.sub(r"['\"]", '', arg_str)

    # 3. Whitelist allowed characters.
    # Allows alphanumeric, dash, underscore, colon (for IPs/paths),
    # dot, slashes (for paths), and spaces (for paths with spaces).
    sanitized = re.sub(r'[^a-zA-Z0-9\-_:./\\\s]', '', sanitized)

    # 4. Block argument injection prefixes
    stripped_arg = sanitized.lstrip()

    if stripped_arg.startswith('-'):
        logger.warning(f"Blocked potential argument injection (prefix '-'): {_sanitize_for_logging(arg_str)}")
        return ""

    if stripped_arg.startswith('/'):
        # Block arguments that start with '/' AND contain a space,
        # as this is a common injection pattern (e.g., "/c calc.exe").
        # This still allows valid *NIX paths (e.g., "/var/log").
        if ' ' in stripped_arg:
            logger.warning(f"Blocked potential argument injection (prefix '/' with space): {_sanitize_for_logging(arg_str)}")
            return ""

    return sanitized


def sanitize_csv_cell(cell_value: Any) -> str:
    """
    Sanitizes a value to prevent CSV Injection (formula injection)
    when opening the file in spreadsheet software.
    """
    if cell_value is None:
        return ""
    str_val = str(cell_value)

    # Prepend an apostrophe if the value starts with a risky character
    if str_val.startswith(('=', '+', '-', '@', '|')):
        return f"'{str_val}"

    return str_val