def plsi(n: int, forms: str) -> str:
    """
    Choose a plural form for Slovenian - or create one, for some rare cases

    `forms` can be a string containing the singular and plural form, separated
    by "|", for instance `"okno|okni|okna|oken".

    The number of forms must be 4 or 3.
    - The four forms are singular, dual, plural for 3 or 4, plural for >= 5
    - Three forms are used for cases other than genitive, where plural is the
      same for all numbers >= 3

    A single form can be given for nouns in genitive that conform to one of
    the following rules:
    - miza/mizi/mize/miz
    - korak/koraka/koraki/korakov
    The function does not speak Slovenian and cannot verify the conformance. :)

    Examples:

    - Four plural forms:
        f'Aktiven {nfilt} {plsi(n, "filter|filtra|filtri|filtrov")}'

    - Four forms, multiple words conjugated:
        f'V tabeli je {n} {plsi(n, "učni primer|učna primera|učni primeri|učnih primerov")}'

    - Three forms (non-nominative):
        f'Datoteka z {n} {plsi(n, "primerom|primeroma|primeri")}'

    - Single form, feminine, using pattern
        f'Najdena {nvars} {plsi(nvars, "spremenljivka")}'

    - Single form, masculine, using pattern
        f'Vsebina: {n} {plsi(n, "primer")'

    - Plural form used twice
        f'{plsi(n, "Ostalo je|Ostala sta|Ostali so")} še {n} {plsi(n, "primer")}'

    Args:
        n: number
        forms: plural forms, separated by "|", or a single (regular) noun

    Returns:
        form corresponding to the given number
    """
    n = abs(n) % 100
    if n == 4:
        n = 3
    elif n == 0 or n >= 5:
        n = 4
    n -= 1

    if "|" in forms:
        forms = forms.split("|")
        # Don't use max: we want it to fail if there are just two forms
        if n == 3 and len(forms) == 3:
            n -= 1
        return forms[n]

    if forms[-1] == "a":
        return forms[:-1] + ("a", "i", "e", "")[n]
    else:
        return forms + ("", "a", "i", "ov")[n]


def plsi_sz(n: int) -> str:
    """
    Returns proposition "s" or "z", depending on the number that will follow it.

    Args:
        n (int): number

    Returns:
        Proposition s or z
    """
    # Cut of all groups of three, except the first one
    lead3 = f"{n:_}".split("_")[0]

    # handle 1, 1_XXX, 1_XXX_XXX ... because "ena" is not pronounced and we need
    # to match "tisoč", "milijon", ... "trilijarda"
    # https://sl.wikipedia.org/wiki/Imena_velikih_%C5%A1tevil
    if lead3 == "1":
        if n > 10 ** 63:  # nobody knows their names
            return "z"
        return "zszzzzsssssssssszzzzzz"[len(str(n)) // 3]

    # This is pronounced sto...something
    if len(lead3) == 3 and lead3[0] == "1":
        return "s"

    # Take the first digit, or the second for two-digit number not divisible by 10
    lead = lead3[len(lead3) == 2 and lead3[1] != "0"]
    return "zzzssssszz"[int(lead)]


def z_besedo(n, case, gender, zero="nič"):
    if not 0 <= n <= 10:
        return str(n)
    if n == 0:
        return zero
    elif n == 1:
        return {"m": ("", "en", "enega", "enemu", "en", "enem", "enim"),
                "f": ("", "ena", "ene", "eni", "eno", "eni", "eno"),
                "n": ("", "eno", "enega", "enemu", "eno", "enem", "enim")}[gender][case]
    elif n == 2:
        return {"m": ("", "dva", "dveh", "dvema", "dva", "dveh", "dvema"),
                "f": ("", "dve", "dveh", "dvema", "dve", "dveh", "dvema"),
                "n": ("", "dve", "dveh", "dvema", "dve", "dveh", "dvema")}[gender][case]
    return (None, None, None,
            ("", "tri", "treh", "trem", "tri", "treh", "tremi"),
            ("", "štiri", "štirih", "štirim", "štiri", "štirih", "štirimi"),
            ("", "pet", "petih", "petim", "pet", "petih", "petimi"),
            ("", "šest", "šestih", "šestim", "šest", "šestih", "šestimi"),
            ("", "sedem", "sedmih", "sedmim", "sedem", "sedmih", "sedmimi"),
            ("", "osem", "osmih", "osmim", "osem", "osmih", "osmimi"),
            ("", "devet", "devetih", "devetim", "devet", "devetih", "devetimi"),
            ("", "deset", "desetih", "desetim", "deset", "desetih", "desetimi"))[n][case]
