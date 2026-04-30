"""Internationalization module — loads translations from YAML locale files."""

import locale
import logging
import os
import sys
from collections.abc import Callable

import yaml

from ..paths import resource_path

logger = logging.getLogger(__name__)

# Global state
_current_lang = "en"
_listeners: list[Callable[[], None]] = []
_translations: dict[str, dict[str, str]] = {}


def _load_locale(lang: str) -> dict[str, str]:
    """Loads a single locale YAML file and returns a flat dict.

    Args:
        lang: Language code (e.g. 'uk', 'en').

    Returns:
        A dict mapping translation keys to translated strings.
    """
    locales_dir = resource_path("src", "i18n", "locales")
    path = os.path.join(locales_dir, f"{lang}.yaml")
    if not os.path.exists(path):
        logger.warning(f"Locale file not found: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse locale '{path}': {e}")
        return {}


def _load_all_translations() -> dict[str, dict[str, str]]:
    """Loads all locale files and merges into {key: {lang: text}} format.

    Returns:
        A nested dict: outer key is the translation key, inner key
        is the language code, value is the translated string.
    """
    merged: dict[str, dict[str, str]] = {}
    for lang in ("uk", "en"):
        locale_data = _load_locale(lang)
        for key, text in locale_data.items():
            if key not in merged:
                merged[key] = {}
            merged[key][lang] = str(text)
    return merged


def detect_language() -> str:
    """Detects the OS UI language automatically.

    Returns:
        'uk' for Ukrainian locale, 'en' otherwise.
    """
    try:
        if sys.platform == "win32":
            import ctypes

            windll = ctypes.windll.kernel32
            lang_code = locale.windows_locale.get(windll.GetUserDefaultUILanguage())
        else:
            lang_code = locale.getdefaultlocale()[0]

        if lang_code and lang_code.startswith("uk"):
            return "uk"
    except Exception:
        pass
    return "en"


# Initial bootstrap
_current_lang = detect_language()
_translations = _load_all_translations()


def t(key: str, **kwargs: object) -> str:
    """Returns a translated string for the given key.

    Args:
        key: The translation key (e.g. 'app.title').
        **kwargs: Format parameters to interpolate into the string.

    Returns:
        The translated and formatted string, or the key itself
        if no translation is found.
    """
    entry = _translations.get(key)
    if not entry:
        return key

    text = entry.get(_current_lang) or entry.get("en") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text


def get_lang() -> str:
    """Returns the current language code."""
    return _current_lang


def set_lang(lang: str) -> None:
    """Sets the active language and notifies all listeners.

    Args:
        lang: Language code ('uk' or 'en').
    """
    global _current_lang
    if lang not in ("uk", "en"):
        return

    _current_lang = lang
    dead_listeners: list[Callable[[], None]] = []
    for listener in _listeners:
        try:
            listener()
        except Exception:
            dead_listeners.append(listener)

    for dead in dead_listeners:
        if dead in _listeners:
            _listeners.remove(dead)


def add_listener(callback: Callable[[], None]) -> None:
    """Registers a callback to be invoked when the language changes.

    Args:
        callback: A no-arg callable (typically a UI rebuild method).
    """
    if callback not in _listeners:
        _listeners.append(callback)


def remove_listener(callback: Callable[[], None]) -> None:
    """Unregisters a previously added language-change callback.

    Args:
        callback: The callback to remove.
    """
    if callback in _listeners:
        _listeners.remove(callback)
