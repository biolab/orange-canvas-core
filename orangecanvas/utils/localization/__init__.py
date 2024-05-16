import os
import json
import importlib

from AnyQt.QtCore import QSettings

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


def get_languages(package=None):
    if package is None:
        package = "orangecanvas"
    package_path = os.path.dirname(importlib.import_module(package).__file__)
    msgs_path = os.path.join(package_path, "i18n")
    if not os.path.exists(msgs_path):
        return []
    return [name
            for name, ext in map(os.path.splitext, os.listdir(msgs_path))
            if ext == ".json"]


def language_changed():
    s = QSettings()
    lang = s.value("application/language", "English")
    last_lang = s.value("application/last-used-language", "English")
    return lang != last_lang


def update_last_used_language():
    s = QSettings()
    lang = s.value("application/language", "English")
    s.setValue("application/last-used-language", lang)


class Translator:
    e = eval

    def __init__(self, package, organization="biolab.si", application="Orange"):
        s = QSettings(QSettings.IniFormat, QSettings.UserScope,
                      organization, application)
        lang = s.value("application/language", "English")
        # For testing purposes (and potential fallback)
        # lang = os.environ.get("ORANGE_LANG", "English")
        package_path = os.path.dirname(importlib.import_module(package).__file__)
        path = os.path.join(package_path, "i18n", f"{lang}.json")
        if not os.path.exists(path):
            path = os.path.join(package_path, "i18n", "English.json")
        assert os.path.exists(path)
        self.m = json.load(open(path))

    def c(self, idx):
        return compile(self.m[idx], '<string>', 'eval')
