import json
import logging
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Set

from src.config.config import CONFIG, get_project_root

logger = logging.getLogger(__name__)

_current_lang_code: str = "en"
_translations: Dict[str, str] = {}
LANG_MAP: Dict[str, str] = {}
_translation_key_cache: Dict[str, Set[str]] = {}


def get_translations_dir() -> str:
    """
    Determines the path to the translations directory, whether running
    from source (in 'src') or as a frozen .exe (in root).
    """
    project_root: str = get_project_root()
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running as a frozen executable (PyInstaller bundle)
        # We configure the .spec file to place 'translations' in the root.
        return os.path.join(project_root, "translations")
    else:
        # Running from source, files are located in 'src/translations'
        return os.path.join(project_root, "src", "translations")


TRANSLATIONS_DIR: str = get_translations_dir()


def _load_lang_map() -> None:
    """Loads the language code to language name mapping file."""
    global LANG_MAP
    try:
        map_path: str = os.path.join(TRANSLATIONS_DIR, "lang_map.json")
        with open(map_path, "r", encoding="utf-8-sig") as f:
            LANG_MAP = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load lang_map.json from {TRANSLATIONS_DIR}: {e}")
        LANG_MAP = {"en": "English"}  # Fallback


def _load_translations() -> None:
    """Loads the translation strings for the current language."""
    global _translations

    def load_json(lang_code: str) -> Dict[str, Any]:
        """Helper to load a single JSON translation file."""
        file_path: str = os.path.join(TRANSLATIONS_DIR, f"{lang_code}.json")
        if not os.path.exists(file_path):
            logger.warning(f"Translation file not found: {file_path}")
            return {}
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load translation {lang_code}: {e}")
            return {}

    # Always load English as the fallback
    base_translations: Dict[str, Any] = load_json("en")
    merged_translations: Dict[str, Any] = base_translations.copy()

    # Overlay the target language on top of English
    if _current_lang_code != "en":
        target_translations: Dict[str, Any] = load_json(_current_lang_code)
        merged_translations.update(target_translations)

    _translations = merged_translations
    logger.info(
        f"Translations loaded for language: '{_current_lang_code}' from {TRANSLATIONS_DIR}"
    )


def switch_language(lang_code: str) -> bool:
    """Switches the active language and reloads translations."""
    global _current_lang_code
    if lang_code and lang_code in LANG_MAP:
        if lang_code != _current_lang_code:
            logger.info(
                f"Switching language from '{_current_lang_code}' to '{lang_code}'"
            )
            _current_lang_code = lang_code
            CONFIG["language"] = lang_code
        _load_translations()  # Reload translations
        return True
    logger.warning(f"Attempted to switch to unsupported language: {lang_code}")
    return False


def translate(key: str) -> str:
    """Gets the translation for a key, falling back to the key itself."""
    return _translations.get(key, key)


def get_all_translations_for_key(key: str) -> Set[str]:
    """
    Gets all translated values for a specific key from all .json files.
    Used for validating combobox/placeholder inputs.
    """
    global _translation_key_cache
    if key in _translation_key_cache:
        return _translation_key_cache[key]

    placeholders: Set[str] = set()
    try:
        placeholders.add(key)  # Add the key itself as a valid value

        for file_name in os.listdir(TRANSLATIONS_DIR):
            if file_name.endswith(".json") and file_name != "lang_map.json":
                file_path: str = os.path.join(TRANSLATIONS_DIR, file_name)
                try:
                    with open(file_path, "r", encoding="utf-8-sig") as f:
                        data: Dict[str, Any] = json.load(f)
                        if key in data:
                            placeholders.add(data[key])
                except Exception as e:
                    logger.error(f"Failed to parse {file_name} for key '{key}': {e}")
    except Exception as e:
        logger.error(f"Failed to build placeholder list for key '{key}': {e}")

    _translation_key_cache[key] = placeholders
    return placeholders


def get_available_languages() -> List[Dict[str, str]]:
    """Returns a sorted list of available languages for display."""
    if not LANG_MAP:
        _load_lang_map()

    langs: List[Dict[str, str]] = [
        {"code": code, "name": name} for code, name in LANG_MAP.items()
    ]

    # Sort by display name
    langs.sort(key=lambda x: x["name"])

    # Ensure 'en' is always first in the list
    en_lang: Optional[Dict[str, str]] = next(
        (lang for lang in langs if lang["code"] == "en"), None
    )
    if en_lang:
        langs.remove(en_lang)
        langs.insert(0, en_lang)

    return langs


# --- Initial Load ---
_load_lang_map()
_current_lang_code = CONFIG.get("language", "en")
_load_translations()
