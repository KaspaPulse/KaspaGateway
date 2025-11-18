#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Provides validation, sanitization, and helper functions for user input
and other data.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from src.utils.i18n import get_all_translations_for_key

logger = logging.getLogger(__name__)

# This is loaded at runtime, so we initialize it here.
# It's used to prevent validating placeholder text as a real address.
_address_placeholders: Set[str] = get_all_translations_for_key(
    "Enter Kaspa Address or Select from Dropdown"
)

_SENSITIVE_KEYS: Set[str] = {
    "key",
    "apikey",
    "token",
    "secret",
    "auth",
    "password",
    "signature",
    "private",
    "pin",
}
_SENSITIVE_KEY_PATTERN: re.Pattern = re.compile(
    "|".join(_SENSITIVE_KEYS), re.IGNORECASE
)


def _sanitize_for_logging(log_message: Any) -> str:
    """
    Sanitizes a simple message for logging, removing newlines.
    Converts non-string inputs to string safely.
    """
    if not isinstance(log_message, str):
        try:
            log_message = str(log_message)
        except Exception:
            return "[Unloggable Content]"
    return log_message.replace("\n", " ").replace("\r", " ")


def sanitize_data_for_logging(data: Any) -> Any:
    """
    Recursively sanitizes dictionaries, lists, or strings to remove sensitive values
    based on keywords in dictionary keys.
    """
    if isinstance(data, dict):
        clean_dict: Dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(k, str) and _SENSITIVE_KEY_PATTERN.search(k):
                clean_dict[k] = "***REDACTED***"
            else:
                clean_dict[k] = sanitize_data_for_logging(v)
        return clean_dict
    elif isinstance(data, list):
        return [sanitize_data_for_logging(item) for item in data]
    elif isinstance(data, str):
        return _sanitize_for_logging(data)
    else:
        # For other types (int, float, bool, None), return as is
        return data


def validate_kaspa_address(address: str) -> bool:
    """
    Validates a Kaspa address string against the 'kaspa:' prefix and
    bech32m-like pattern. Also checks against known placeholder strings
    and enforces strict length limits to prevent buffer overflows.
    """
    global _address_placeholders
    if not _address_placeholders:
        _address_placeholders = get_all_translations_for_key(
            "Enter Kaspa Address or Select from Dropdown"
        )

    if not isinstance(address, str) or not address:
        return False

    # FIX 1: Enforce maximum length to prevent DoS/Overflows
    # Kaspa addresses are typically around 60-90 chars. 130 is a safe upper bound.
    if len(address) > 130:
        return False

    address_lower: str = address.lower().strip()

    if address in _address_placeholders:
        return False

    # Pattern for kaspa:bech32m
    pattern: str = r"^kaspa:[qpzry9x8gf2tvdw0s3jn54khce6mua7l]+$"
    is_valid: bool = re.match(pattern, address_lower) is not None

    if not is_valid:
        if address not in _address_placeholders:
            logger.warning(
                f"Address validation FAILED for: {_sanitize_for_logging(address)}"
            )

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
    Supports IPv4, IPv6 (in brackets), hostnames, and empty host (e.g., :port).
    Returns (host, port) tuple if valid, else None.
    """
    if not ip_port:
        return None

    # Regex to match:
    # 1. [ipv6]:port (e.g., [::1]:16110)
    # 2. host.name:port (e.g., localhost:16110)
    # 3. 127.0.0.1:port
    # 4. :port (e.g., :16110)
    match: Optional[re.Match[str]] = re.match(
        r"^(?:(\[.+\]|[\w\.\-]+))?:(\d+)$", ip_port.strip()
    )
    if not match:
        return None

    ip_or_host: str = match.group(1) if match.group(1) else ""
    port: str = match.group(2)

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
    allowing alphanumeric, spaces, basic symbols, and dots.
    Enforces a length limit.
    """
    if not isinstance(input_str, str):
        return ""

    # FIX 2: Allowed dot (.) in regex whitelist for filenames/extensions
    # Whitelist alphanumeric, space, dash, underscore, parentheses, dot
    sanitized: str = re.sub(r"[^a-zA-Z0-9 \-_().]", "", input_str)

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
    if ".." in arg_str:
        logger.warning(
            f"Blocked potential path traversal: {_sanitize_for_logging(arg_str)}"
        )
        return ""

    # 2. Remove simple quotes. Stricter sanitization will follow.
    sanitized: str = re.sub(r"['\"]", "", arg_str)

    # 3. Whitelist allowed characters.
    # Allows alphanumeric, dash, underscore, colon (for IPs/paths),
    # dot, slashes (for paths), spaces (for paths), and brackets (for IPv6).
    sanitized = re.sub(r"[^a-zA-Z0-9\-_:./\\\[\]\s]", "", sanitized)

    # 4. Block argument injection prefixes
    stripped_arg: str = sanitized.lstrip()

    if stripped_arg.startswith("-"):
        logger.warning(
            f"Blocked potential argument injection (prefix '-'): {_sanitize_for_logging(arg_str)}"
        )
        return ""

    if stripped_arg.startswith("/"):
        # Block arguments that start with '/' AND contain a space,
        # as this is a common injection pattern (e.g., "/c calc.exe").
        # This still allows valid *NIX paths (e.g., "/var/log").
        if " " in stripped_arg:
            logger.warning(
                f"Blocked potential argument injection (prefix '/' with space): {_sanitize_for_logging(arg_str)}"
            )
            return ""

    return sanitized


def sanitize_csv_cell(cell_value: Any) -> str:
    """
    Sanitizes a value to prevent CSV Injection (formula injection)
    when opening the file in spreadsheet software.
    """
    if cell_value is None:
        return ""
    str_val: str = str(cell_value)

    # Prepend an apostrophe if the value starts with a risky character
    if str_val.startswith(("=", "+", "-", "@", "|")):
        return f"'{str_val}"

    return str_val
