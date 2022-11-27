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
