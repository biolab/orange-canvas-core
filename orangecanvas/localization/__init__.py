from functools import lru_cache
import warnings

import os
import json
import importlib

try:
    from AnyQt.QtCore import QSettings, QLocale
except ImportError:
    QSettings = QLocale = None


def pl(n: int, forms: str) -> str:  # pylint: disable=invalid-name
    """
    Choose a singular/plural form for English - or create one, for regular nouns

    `forms` can be a string containing the singular and plural form, separated
    by "|", for instance `pl(n, "leaf|leaves")`.

    For nouns that are formed by adding an -s (e.g. tree -> trees),
    and for nouns that end with -y that is replaced by -ies
    (dictionary -> dictionaries), it suffices to pass the noun,
    e.g. `pl(n, "tree")`, `pl(n, "dictionary")`.

    Args:
        n: number
        forms: plural forms, separated by "|", or a single (regular) noun

    Returns:
        form corresponding to the given number
    """
    plural = int(n != 1)

    if "|" in forms:
        return forms.split("|")[plural]

    if forms[-1] in "yY" and forms[-2] not in "aeiouAEIOU":
        word = [forms, forms[:-1] + "ies"][plural]
    else:
        word = forms + "s" * plural
    if forms.isupper():
        word = word.upper()
    return word

def _load_json(path):
    with open(path) as handle:
        return json.load(handle)

@lru_cache
def get_languages(package=None):
    if package is None:
        package = "orangecanvas"
    package_path = os.path.dirname(importlib.import_module(package).__file__)
    msgs_path = os.path.join(package_path, "i18n")
    if not os.path.exists(msgs_path):
        return {}
    names = {}
    for name, ext in map(os.path.splitext, os.listdir(msgs_path)):
        if ext == ".json":
            try:
                msgs = _load_json(os.path.join(msgs_path, name + ext))
            except json.JSONDecodeError:
                warnings.warn("Invalid language file "
                              + os.path.join(msgs_path, name + ext))
            else:
                names[msgs[0]] = name
    return names


if QLocale is not None:
    DEFAULT_LANGUAGE = QLocale().languageToString(QLocale().language())
    if DEFAULT_LANGUAGE not in get_languages():
        DEFAULT_LANGUAGE = "English"
else:
    DEFAULT_LANGUAGE = "English"


def language_changed():
    assert QSettings is not None

    s = QSettings()
    lang = s.value("application/language", DEFAULT_LANGUAGE)
    last_lang = s.value("application/last-used-language", DEFAULT_LANGUAGE)
    return lang != last_lang


def update_last_used_language():
    assert QSettings is not None

    s = QSettings()
    lang = s.value("application/language", "English")
    s.setValue("application/last-used-language", lang)


class _list(list):
    # Accept extra argument to allow for the original string
    def __getitem__(self, item):
        if isinstance(item, tuple):
            item = item[0]
        return super().__getitem__(item)


class Translator:
    e = eval

    def __init__(self, package, organization="biolab.si", application="Orange"):
        if QSettings is not None:
            s = QSettings(QSettings.IniFormat, QSettings.UserScope,
                          organization, application)
            lang = s.value("application/language", DEFAULT_LANGUAGE)
        else:
            lang = DEFAULT_LANGUAGE
        # For testing purposes (and potential fallback)
        # lang = os.environ.get("ORANGE_LANG", "English")
        package_path = os.path.dirname(importlib.import_module(package).__file__)
        lang_eng = get_languages().get(lang, lang)
        path = os.path.join(package_path, "i18n", f"{lang_eng}.json")
        if not os.path.exists(path):
            path = os.path.join(package_path, "i18n", f"{DEFAULT_LANGUAGE}.json")
        assert os.path.exists(path), f"Missing language file {path}"
        self.m = _list(_load_json(path))

    # Extra argument(s) can give the original string or any other relevant data
    def c(self, idx, *_):
        return compile(self.m[idx], '<string>', 'eval')
