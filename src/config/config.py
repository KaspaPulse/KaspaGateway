# File: src/config/config.py
"""
Handles loading, saving, and providing access to the application's configuration.
"""

from __future__ import annotations

import base64
import getpass
import json
import logging
import os
import sys
from typing import Any, Dict, List, MutableMapping, Optional

import keyring

logger = logging.getLogger(__name__)

# Application Constants
APP_VERSION: str = "1.0.0"
APP_NAME: str = "KaspaGateway"

# Global Configuration State
USER_DATA_ROOT: str = ""
CONFIG_FILE: str = ""
CONFIG: Dict[str, Any] = {}
DEFAULT_CONFIG: Dict[str, Any] = {}

# --- Constants & Defaults ---

SUPPORTED_CURRENCIES: List[str] = [
    "usd", "sar", "eur", "gbp", "chf", "aud", "cad", "jpy", "krw", "rub",
    "cny", "try", "inr", "idr", "hkd", "sgd", "brl",
]

SUPPORTED_LANGUAGES: List[str] = [
    "en", "ar", "ru", "tr", "de", "es", "fr", "hi", "ja", "ko", "zh-CN", "id",
]

SUPPORTED_TABS: List[str] = [
    "Explorer",
    "Kaspa Node",
    "Kaspa Bridge",
    "Analysis",
    "Top Addresses",
    "Log",
]

CURRENCY_SYMBOLS: Dict[str, str] = {
    "usd": "$", "sar": "SAR", "eur": "€", "gbp": "£", "chf": "CHF",
    "aud": "A$", "cad": "C$", "jpy": "¥", "krw": "₩", "rub": "₽",
    "cny": "¥", "try": "₺", "inr": "₹", "idr": "Rp", "hkd": "HK$",
    "sgd": "S$", "brl": "R$",
}

CURRENCY_TRANSLATION_KEYS: Dict[str, str] = {
    "usd": "currency_usd", "sar": "currency_sar", "eur": "currency_eur",
    "gbp": "currency_gbp", "chf": "currency_chf", "aud": "currency_aud",
    "cad": "currency_cad", "jpy": "currency_jpy", "krw": "currency_krw",
    "rub": "currency_rub", "cny": "currency_cny", "try": "currency_try",
    "inr": "currency_inr", "idr": "currency_idr", "hkd": "currency_hkd",
    "sgd": "currency_sgd", "brl": "currency_brl",
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
        "kaspad": "/info/kaspad",
    },
    "explorer": {
        "address": "https://explorer.kaspa.org/addresses/{kaspaAddress}",
        "transaction": "https://explorer.kaspa.org/txs/{txid}",
    },
    "external": {
        "coingecko": "https://api.coingecko.com/api/v3/simple/price?ids=kaspa&vs_currencies={supported_currencies}",
        "api_key": "",
    },
}

# --- Helper Functions ---

def _get_keyring_service_name() -> str:
    try:
        username: str = getpass.getuser()
    except Exception:
        username = "default_user"
    return f"{APP_NAME}-{username}"

def get_project_root() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def get_assets_path(relative_path: str) -> str:
    return os.path.join(get_project_root(), "assets", relative_path)

def get_user_data_root(custom_path: Optional[str] = None) -> str:
    default_root: str = os.path.join(
        os.getenv("LOCALAPPDATA", os.getenv("APPDATA", "")), APP_NAME
    )
    path: str = default_root
    use_default: bool = False

    if custom_path:
        if '"' in custom_path:
            logger.error('Invalid custom_path. Falling back to default.')
            use_default = True
        else:
            try:
                safe_root_abs: str = os.path.abspath(default_root)
                user_path_abs: str = os.path.abspath(custom_path)
                if user_path_abs.startswith(safe_root_abs) or os.path.isabs(user_path_abs):
                    path = user_path_abs
                    logger.info(f"Using custom user data path: {path}")
                else:
                    logger.warning("Custom path suspicious. Falling back.")
                    use_default = True
            except Exception as e:
                logger.error(f"Error processing custom_path: {e}")
                use_default = True

    if use_default:
        path = os.path.abspath(default_root)

    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        logger.critical(f"Could not create user data directory: {e}")
        path = os.path.abspath(os.path.join(get_project_root(), "user_data"))
        os.makedirs(path, exist_ok=True)
    return path

# --- Encryption / Decryption ---

def _encrypt(data: str) -> str:
    if not data:
        return ""
    service: str = _get_keyring_service_name()
    username: str = "api_key"
    try:
        keyring.set_password(service, username, data)
        return f"keyring_managed:{service}:{username}"
    except Exception as e:
        logger.error(f"Keyring encryption failed: {e}")
        return data

def _decrypt(data: str) -> str:
    if not data:
        return ""
    if data.startswith("keyring_managed:"):
        try:
            _, service, username = data.split(":", 2)
            key: Optional[str] = keyring.get_password(service, username)
            return key if key else ""
        except Exception as e:
            logger.error(f"Keyring decryption failed: {e}")
            return ""
    try:
        base64.b64decode(data.encode("utf-8"))
        return ""
    except Exception:
        return data

def _recursive_encrypt(d: Any) -> Any:
    if isinstance(d, dict):
        new_dict: Dict[str, Any] = {}
        for k, v in d.items():
            if k == "api_key" and isinstance(v, str):
                new_dict[k] = _encrypt(v)
            else:
                new_dict[k] = _recursive_encrypt(v)
        return new_dict
    elif isinstance(d, list):
        return [_recursive_encrypt(item) for item in d]
    return d

def _recursive_decrypt(d: Any) -> Any:
    if isinstance(d, dict):
        new_dict: Dict[str, Any] = {}
        for k, v in d.items():
            if k == "api_key" and isinstance(v, str):
                new_dict[k] = _decrypt(v)
            else:
                new_dict[k] = _recursive_decrypt(v)
        return new_dict
    elif isinstance(d, list):
        return [_recursive_decrypt(item) for item in d]
    return d

# --- Configuration Management ---

def _initialize_defaults(user_data_root: str) -> None:
    global DEFAULT_CONFIG
    DEFAULT_CONFIG = {
        "version": APP_VERSION,
        "language": "en",
        "log_level": "INFO",
        "theme": "superhero",
        "selected_currency": "USD",
        "table_font_size": 9,
        "analysis_font_size": 9,
        "check_for_updates": True,
        "autostart_on_windows": False,
        "paths": {
            "database": os.path.join(user_data_root, "data"),
            "export": os.path.join(user_data_root, "exports"),
            "log": os.path.join(user_data_root, "logs"),
            "backup": os.path.join(user_data_root, "backups"),
        },
        "db_filenames": {
            "transactions": "Transactions.duckdb",
            "addresses": "Addresses.duckdb",
            "app_data": "AppData.duckdb",
        },
        "performance": {
            "timeout": 30,
            "retry_attempts": 5,
            "backoff_factor": 4.0,
            "max_workers": 10,
            "max_pages": 10000,
            "page_delay": 0.05,
            "price_cache_hours": 0.25,
            "network_cache_hours": 0.25,
            "auto_refresh_enabled": False,
            "auto_refresh_interval_seconds": 60,
        },
        "api": {
            "active_profile": "Default",
            "profiles": {"Default": DEFAULT_API_PROFILE},
        },
        "links": {
            "donation": "https://explorer.kaspa.org/addresses/kaspa:qz0yqq8z3twwgg7lq2mjzg6w4edqys45w2wslz7tym2tc6s84580vvx9zr44g",
            "twitter": "https://x.com/KaspaPulse",
            "github": "https://github.com/KaspaPulse/KaspaGateway",
        },
        "display": {
            "supported_currencies": SUPPORTED_CURRENCIES,
            "displayed_languages": SUPPORTED_LANGUAGES,
            "displayed_currencies": SUPPORTED_CURRENCIES,
            "displayed_tabs": SUPPORTED_TABS,
        },
        "kaspa_node": {},
        "kaspa_bridge": {"enable_bridge_2": False},
    }

def _recursive_update(d: MutableMapping[str, Any], u: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for k, v in u.items():
        if isinstance(v, MutableMapping):
            d[k] = _recursive_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d

def _migrate_config(user_config: Dict[str, Any]) -> Dict[str, Any]:
    if "api" in user_config and "profiles" not in user_config.get("api", {}):
        logger.warning("Migrating old API config.")
        old_api_config = user_config.pop("api", {})
        migrated_api = json.loads(json.dumps(DEFAULT_API_PROFILE))
        migrated_api["base_url"] = old_api_config.get("base_url", DEFAULT_API_PROFILE["base_url"])
        for k in ["endpoints", "explorer", "external"]:
            if k in old_api_config:
                migrated_api[k].update(old_api_config[k])
        user_config["api"] = {
            "active_profile": "Default",
            "profiles": {"Default": migrated_api},
        }
    return _recursive_decrypt(user_config)

def _save_config_file(config: Dict[str, Any]) -> None:
    """
    Saves the config.json to disk.
    CRITICAL: Always forces 'version' to APP_VERSION (1.0.0) on disk
    to prevent git hashes or dev tags from breaking version checks later.
    """
    try:
        encrypted_config = _recursive_encrypt(config)
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        
        # Force clean version on disk
        encrypted_config["version"] = APP_VERSION
        
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(encrypted_config, f, indent=4, sort_keys=True)
        logger.info(f"Configuration saved to {CONFIG_FILE}")
    except OSError as e:
        logger.error(f"Failed to save configuration: {e}")
        raise

def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        _save_config_file(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_config = json.load(f)

        user_config = _migrate_config(user_config)
        final_config = json.loads(json.dumps(DEFAULT_CONFIG))
        final_config = _recursive_update(final_config, user_config)

        if final_config.get("version") != APP_VERSION:
            logger.warning(f"Version mismatch. Upgrading config to {APP_VERSION}...")
            final_config["version"] = APP_VERSION
            _save_config_file(final_config)

        return final_config

    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Error reading config file: {e}. Reverting to defaults.")
        _save_config_file(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def get_active_api_config() -> Dict[str, Any]:
    active_profile = CONFIG.get("api", {}).get("active_profile", "Default")
    return CONFIG.get("api", {}).get("profiles", {}).get(active_profile, DEFAULT_API_PROFILE)

def initialize_config(custom_path: Optional[str] = None) -> None:
    global USER_DATA_ROOT, CONFIG_FILE, CONFIG
    USER_DATA_ROOT = get_user_data_root(custom_path)
    CONFIG_FILE = os.path.join(USER_DATA_ROOT, "config.json")
    _initialize_defaults(USER_DATA_ROOT)
    CONFIG.clear()
    CONFIG.update(load_config())
