# File: src/config/config.py
"""
Handles loading, saving, and providing access to the application's configuration.
This module is responsible for:
- Defining default settings.
- Locating and managing user data paths.
- Loading user 'config.json' from disk.
- Merging user config with defaults.
- Handling secure credential storage (API keys) using 'keyring'.
- Migrating old config formats to new ones.
"""

from __future__ import annotations

import json
import os
import logging
import sys
import base64
import getpass
import keyring
from typing import Dict, Any, List, MutableMapping, Optional, Tuple
from functools import reduce
from operator import getitem

logger = logging.getLogger(__name__)

APP_VERSION = "1.0.0"
APP_NAME = "KaspaGateway"


def _get_keyring_service_name() -> str:
    """Generates a unique service name for keyring based on the app and user."""
    try:
        username = getpass.getuser()
    except Exception:
        username = "default_user"
    return f"{APP_NAME}-{username}"


def get_project_root() -> str:
    """Gets the root directory of the project, handling both source and bundled (PyInstaller) execution."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as a PyInstaller bundle
        return sys._MEIPASS
    # Running as a normal script
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def get_assets_path(relative_path: str) -> str:
    """Gets the full path to a file in the 'assets' directory."""
    return os.path.join(get_project_root(), 'assets', relative_path)


def get_user_data_root(custom_path: Optional[str] = None) -> str:
    """
    Determines and creates the root directory for user data (config, logs, db).
    
    This function contains a security check to ensure that if a 'custom_path'
    is provided via the CLI, it MUST be a subdirectory of the default
    %APPDATA%/KaspaGateway folder. This prevents arbitrary file writes
    to other locations on the file system.
    """
    default_root = os.path.join(os.getenv('APPDATA', ''), APP_NAME)
    path = default_root

    if custom_path:
        try:
            # Resolve paths to their absolute, normalized form
            safe_root_abs = os.path.abspath(default_root)
            user_path_abs = os.path.abspath(custom_path)

            # Security Check: Ensure the custom path is a subdirectory of the default APPDATA root.
            # This prevents arbitrary file writes (e.g., --user-data-path "C:\")
            if user_path_abs.startswith(safe_root_abs):
                path = user_path_abs
                logger.info(f"Using custom user data path: {path}")
            else:
                logger.error(
                    f"Invalid custom_path (not a subdirectory of {safe_root_abs}). "
                    f"Falling back to default."
                )
                path = safe_root_abs
        except Exception as e:
            logger.error(
                f"Error processing custom_path '{custom_path}': {e}. "
                f"Falling back to default."
            )
            path = os.path.abspath(default_root)

    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        logger.critical(f"Could not create user data directory at {path}: {e}")
        # Fallback to a local directory within the project/bundle
        path = os.path.abspath(os.path.join(get_project_root(), 'user_data'))
        os.makedirs(path, exist_ok=True)
        logger.warning(f"Falling back to local user data directory: {path}")
    return path


# --- Global Config Variables ---
# These will be initialized by initialize_config()
USER_DATA_ROOT: str = ""
CONFIG_FILE: str = ""
CONFIG: Dict[str, Any] = {}
DEFAULT_CONFIG: Dict[str, Any] = {}
# --- End Global Config Variables ---


SUPPORTED_CURRENCIES: List[str] = [
    "usd", "sar", "eur", "gbp", "chf", "aud", "cad", "jpy", "krw", "rub",
    "cny", "try", "inr", "idr", "hkd", "sgd", "brl"
]
SUPPORTED_LANGUAGES: List[str] = [
    'en', 'ar', 'ru', 'tr', 'de', 'es', 'fr', 'hi', 'ja', 'ko', 'zh-CN', 'id'
]
SUPPORTED_TABS: List[str] = [
    "Explorer", "Kaspa Node", "Kaspa Bridge", "Analysis", "Top Addresses", "Log"
]

CURRENCY_SYMBOLS: Dict[str, str] = {
    'usd': '$', 'sar': 'SAR', 'eur': '€', 'gbp': '£', 'chf': 'CHF', 'aud': 'A$', 'cad': 'C$',
    'jpy': '¥', 'krw': '₩', 'rub': '₽', 'cny': '¥', 'try': '₺', 'inr': '₹', 'idr': 'Rp', 'hkd': 'HK$',
    'sgd': 'S$', 'brl': 'R$'
}
CURRENCY_TRANSLATION_KEYS: Dict[str, str] = {
    'usd': 'currency_usd', 'sar': 'currency_sar', 'eur': 'currency_eur', 'gbp': 'currency_gbp',
    'chf': 'currency_chf', 'aud': 'currency_aud', 'cad': 'currency_cad', 'jpy': 'currency_jpy',
    'krw': 'currency_krw', 'rub': 'currency_rub', 'cny': 'currency_cny', 'try': 'currency_try',
    'inr': 'currency_inr', 'idr': 'currency_idr', 'hkd': 'currency_hkd', 'sgd': 'currency_sgd',
    'brl': 'currency_brl'
}

DEFAULT_API_PROFILE: Dict[str, Any] = {
    "base_url": "https://api.kaspa.org",
    "page_limit": 500,
    "endpoints": {
        "balance": "/addresses/{kaspaAddress}/balance",
        "full_transactions": "/addresses/{kaspaAddress}/full-transactions?limit={limit}&offset={offset}&resolve_previous_outpoints=full",
        "top_addresses": "/addresses/top?limit=1",
        "address_names": "/addresses/names",
        "blockdag_info": "/info/blockdag",
        "blockreward": "/info/blockreward?stringOnly=false",
        "coinsupply": "/info/coinsupply",
        "halving": "/info/halving",
        "hashrate": "/info/hashrate",
        "max_hashrate": "/info/hashrate/max",
        "network": "/info/network",
        "kaspad": "/info/kaspad"
    },
    "explorer": {
        "address": "https://explorer.kaspa.org/addresses/{kaspaAddress}",
        "transaction": "https://explorer.kaspa.org/txs/{txid}"
    },
    "external": {
        "coingecko": "https://api.coingecko.com/api/v3/simple/price?ids=kaspa&vs_currencies={supported_currencies}",
        "api_key": ""
    }
}


def _encrypt(data: str) -> str:
    """Encrypts data using the OS keyring."""
    if not data:
        return ""

    service = _get_keyring_service_name()
    username = "api_key"
    try:
        keyring.set_password(service, username, data)
        logger.info("API key successfully migrated to secure OS keyring.")
        return f"keyring_managed:{service}:{username}"
    except Exception as e:
        logger.error(f"Keyring encryption failed: {e}. API key will be stored unencrypted as a fallback.")
        return data


def _decrypt(data: str) -> str:
    """Decrypts data from the OS keyring or handles legacy/unencrypted data."""
    if not data:
        return ""

    if data.startswith("keyring_managed:"):
        try:
            _, service, username = data.split(":", 2)
            key = keyring.get_password(service, username)
            return key if key else ""
        except Exception as e:
            logger.error(f"Keyring decryption failed: {e}. Key might be lost or inaccessible.")

    # Check for legacy encrypted (base64) format
    try:
        base64.b64decode(data.encode('utf-8'))
        logger.warning(
            "Legacy encrypted (win32crypt) API key detected. This format is no longer supported. "
            "Please re-enter your API key to migrate it to the new secure storage."
        )
        return ""  # Force user to re-enter
    except Exception:
        # If it's not base64, it's likely an old unencrypted key.
        logger.warning("Unencrypted API key detected in config file. Attempting to migrate to secure OS keyring...")
        return data


def _recursive_encrypt(d: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Recursively finds and encrypts 'api_key' fields."""
    if isinstance(d, dict):
        new_dict = {}
        for k, v in d.items():
            if k == 'api_key' and isinstance(v, str):
                new_dict[k] = _encrypt(v)
            else:
                new_dict[k] = _recursive_encrypt(v)
        return new_dict
    elif isinstance(d, list):
        return [_recursive_encrypt(item) for item in d]
    return d


def _recursive_decrypt(d: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Recursively finds and decrypts 'api_key' fields."""
    if isinstance(d, dict):
        new_dict = {}
        for k, v in d.items():
            if k == 'api_key' and isinstance(v, str):
                new_dict[k] = _decrypt(v)
            else:
                new_dict[k] = _recursive_decrypt(v)
        return new_dict
    elif isinstance(d, list):
        return [_recursive_decrypt(item) for item in d]
    return d


def _initialize_defaults(user_data_root: str) -> None:
    """Sets the global DEFAULT_CONFIG dictionary."""
    global DEFAULT_CONFIG
    DEFAULT_CONFIG = {
        "version": APP_VERSION,
        "language": "en",
        "theme": "superhero",
        "selected_currency": "USD",
        "table_font_size": 9,
        "analysis_font_size": 9,
        "logging_level": "INFO",
        "check_for_updates": True,
        "autostart_on_windows": False,
        "paths": {
            "database": os.path.join(user_data_root, 'data'),
            "export": os.path.join(user_data_root, 'exports'),
            "log": os.path.join(user_data_root, 'logs'),
            "backup": os.path.join(user_data_root, 'backups'),
        },
        "db_filenames": {
            "transactions": "Transactions.duckdb",
            "addresses": "Addresses.duckdb",
            "app_data": "AppData.duckdb",
        },
        "performance": {
            "timeout": 30, "retry_attempts": 5, "backoff_factor": 0.5,
            "max_workers": 10, "max_pages": 10000, "page_delay": 0.05,
            "price_cache_hours": 0.25, "network_cache_hours": 0.25,
            "auto_refresh_enabled": False, "auto_refresh_interval_seconds": 60,
        },
        "api": {
            "active_profile": "Default",
            "profiles": {
                "Default": DEFAULT_API_PROFILE
            }
        },
        "links": {
            "donation": "https://explorer.kaspa.org/addresses/kaspa:qz0yqq8z3twwgg7lq2mjzg6w4edqys45w2wslz7tym2tc6s84580vvx9zr44g",
            "twitter": "https://x.com/KaspaPulse",
            "github": "https://github.com/KaspaPulse/KaspaGateway"
        },
        "display": {
            "supported_currencies": SUPPORTED_CURRENCIES,
            "displayed_languages": SUPPORTED_LANGUAGES,
            "displayed_currencies": SUPPORTED_CURRENCIES,
            "displayed_tabs": SUPPORTED_TABS
        },
        "kaspa_node": {},
        "kaspa_bridge": {"enable_bridge_2": False}
    }


def _recursive_update(d: MutableMapping[str, Any], u: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Recursively updates a dictionary."""
    for k, v in u.items():
        if isinstance(v, MutableMapping):
            d[k] = _recursive_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def _migrate_config(user_config: Dict[str, Any]) -> Dict[str, Any]:
    """Migrates old config structures to new ones."""
    # Migration for API profiles
    if 'api' in user_config and 'profiles' not in user_config.get('api', {}):
        logger.warning("Old API config format detected. Migrating to new profile-based structure.")
        old_api_config = user_config.pop('api', {})
        migrated_api_profile = json.loads(json.dumps(DEFAULT_API_PROFILE))
        migrated_api_profile['base_url'] = old_api_config.get('base_url', DEFAULT_API_PROFILE['base_url'])

        for section_key in ['endpoints', 'explorer', 'external']:
            if section_key in old_api_config and isinstance(old_api_config[section_key], dict):
                migrated_api_profile[section_key].update(old_api_config[section_key])
        user_config['api'] = {
            "active_profile": "Default",
            "profiles": {"Default": migrated_api_profile}
        }
    
    # Decrypt keys after potential structure migration
    user_config = _recursive_decrypt(user_config)
    return user_config


def _save_config_file(config: Dict[str, Any]) -> None:
    """Saves the configuration dictionary to the CONFIG_FILE."""
    try:
        encrypted_config = _recursive_encrypt(config)
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        encrypted_config['version'] = APP_VERSION
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(encrypted_config, f, indent=4, sort_keys=True)
    except OSError as e:
        logger.error(f"Failed to save configuration to '{CONFIG_FILE}': {e}")
        raise


def load_config() -> Dict[str, Any]:
    """Loads config from file, merging with defaults and handling migrations."""
    if not os.path.exists(CONFIG_FILE):
        _save_config_file(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            user_config = json.load(f)

        user_config = _migrate_config(user_config)
        final_config = json.loads(json.dumps(DEFAULT_CONFIG))
        final_config = _recursive_update(final_config, user_config)

        if final_config.get('version') != APP_VERSION:
            logger.warning(
                f"Configuration version mismatch. Upgrading from '{final_config.get('version')}' to '{APP_VERSION}'."
            )
            
            # Preserve user's API profiles but update default endpoints
            user_profiles = final_config.get('api', {}).get('profiles', {})
            default_api_config = json.loads(json.dumps(DEFAULT_CONFIG['api']))
            final_config['api'] = default_api_config
            final_config['api']['profiles'].update(user_profiles)
            
            if final_config['api']['active_profile'] not in final_config['api']['profiles']:
                final_config['api']['active_profile'] = "Default"
            
            final_config['version'] = APP_VERSION
            _save_config_file(final_config)
            logger.info("Configuration file has been upgraded to the new version.")

        return final_config
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Error reading config file '{CONFIG_FILE}': {e}. Reverting to defaults.")
        _save_config_file(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()


def get_active_api_config() -> Dict[str, Any]:
    """Gets the currently active API profile configuration."""
    active_profile_name = CONFIG.get('api', {}).get('active_profile', 'Default')
    return CONFIG.get('api', {}).get('profiles', {}).get(active_profile_name, DEFAULT_API_PROFILE)


def initialize_config(custom_path: Optional[str] = None) -> None:
    """
    Initializes the configuration system by setting paths, loading defaults,
    and loading the user's config into the global CONFIG variable.
    """
    global USER_DATA_ROOT, CONFIG_FILE, CONFIG
    USER_DATA_ROOT = get_user_data_root(custom_path)
    CONFIG_FILE = os.path.join(USER_DATA_ROOT, 'config.json')
    _initialize_defaults(USER_DATA_ROOT)
    CONFIG.clear()
    CONFIG.update(load_config())
