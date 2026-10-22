def plde(n: int, forms: str) -> str:
    """
    Choose a singular/plural form for German.

    `forms` can contain singular and plural separated by "|",
    e.g. pl_de(2, "Apfel|Äpfel").

    Only one form may be given for words that adhere to the following rules
      - Words ending in -e → add -n (Katze -> Katzen)
      - Words ending in vowel → add -s
      - Words ending in -el, -en, -er → unchanged
      - Otherwise → add -e

    Args:
        n: number
        forms: plural forms, separated by "|", or a single form
    Returns:
        form corresponding to the given number
    """
    plural = int(n != 1)

    if "|" in forms:
        return forms.split("|")[plural]

    word = forms
    if plural:
        if word[-1] == "e":
            word += "n"
        elif word[-1] in "aiou":
            word += "s"
        elif word.endswith(("el", "en", "er")):
            pass
        else:
            word += "e"
    return word