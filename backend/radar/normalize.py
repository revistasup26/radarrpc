"""Normalización de texto: acentos, entidades HTML, fechas. Clave para el matching."""
from __future__ import annotations

import html
import re
import unicodedata

_ALNUM_SPACE = re.compile(r"[^a-z0-9]+")
_HTML_TAGS = re.compile(r"<[^>]+>")


def unescape(s: str | None) -> str:
    """Limpia entidades HTML (p. ej. &#8217; en abstracts de SciELO) y etiquetas JATS."""
    if not s:
        return ""
    s = html.unescape(s)
    s = _HTML_TAGS.sub(" ", s)
    return " ".join(s.split())


def norm(s: str | None) -> str:
    """Minúsculas, sin acentos, solo caracteres alfanuméricos y espacios.
    'Comunicación Política' -> 'comunicacion politica'. Permite matching insensible a acentos."""
    s = unescape(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return _ALNUM_SPACE.sub(" ", s.lower()).strip()


def tokens(s: str | None) -> list[str]:
    return norm(s).split()


def edit_distance(s1: str, s2: str) -> int:
    """Distancia de Levenshtein con transposición (Damerau-Levenshtein)."""
    if s1 == s2:
        return 0
    len1, len2 = len(s1), len(s2)
    if abs(len1 - len2) > 2:
        return abs(len1 - len2)
    dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    for i in range(len1 + 1):
        dp[i][0] = i
    for j in range(len2 + 1):
        dp[0][j] = j
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and s1[i - 1] == s2[j - 2] and s1[i - 2] == s2[j - 1]:
                dp[i][j] = min(dp[i][j], dp[i - 2][j - 2] + 1)
    return dp[len1][len2]


def word_variants(w: str) -> set[str]:
    """Genera variantes morfológicas y equivalencias español-portugués."""
    wn = norm(w)
    if not wn:
        return set()
    res = {wn}
    # Terminaciones -ción (ES) <-> -ção (PT) y sus plurales
    if wn.endswith("cion"):
        stem = wn[:-4]
        res.update({stem + "cao", stem + "ciones", stem + "coes"})
    elif wn.endswith("cao"):
        stem = wn[:-3]
        res.update({stem + "cion", stem + "ciones", stem + "coes"})
    elif wn.endswith("ciones"):
        stem = wn[:-6]
        res.update({stem + "cion", stem + "cao", stem + "coes"})
    elif wn.endswith("coes"):
        stem = wn[:-4]
        res.update({stem + "cion", stem + "cao", stem + "ciones"})

    # social / sociales / sociais
    if wn in ("social", "sociales", "sociais"):
        res.update({"social", "sociales", "sociais"})

    # digital / digitales / digitais
    if wn in ("digital", "digitales", "digitais"):
        res.update({"digital", "digitales", "digitais"})

    # cientifica / cientifico / cientificas / cientificos
    if any(wn.startswith(prefix) for prefix in ("cientific", "politic", "academic", "tecnologic")):
        base = wn.rstrip("asoe")
        for suffix in ("a", "o", "as", "os"):
            res.add(base + suffix)

    # periodismo <-> jornalismo y variantes
    if "periodis" in wn or "jornalis" in wn:
        res.update({
            "periodismo", "periodista", "periodistas", "periodistica", "periodisticas", "periodistico", "periodisticos",
            "jornalismo", "jornalista", "jornalistas", "jornalistica", "jornalisticas", "jornalistico", "jornalisticos",
        })

    return res



def am_date(d: str | None) -> str | None:
    """Fecha SciELO 'YYYYMMDD' -> ISO 'YYYY-MM-DD'."""
    d = (d or "").strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return d or None


def year_of(d: str | None) -> int | None:
    if not d:
        return None
    d = d.strip()
    if len(d) >= 4 and d[:4].isdigit():
        return int(d[:4])
    return None


# ISO 639-2 (3 letras) -> ISO 639-1 (2 letras), para idiomas frecuentes
_ISO639_2_TO_1 = {
    "spa": "es", "por": "pt", "eng": "en", "fra": "fr", "deu": "de", "ita": "it",
    "cat": "ca", "glg": "gl", "eus": "eu", "nld": "nl", "rus": "ru", "ara": "ar",
    "jpn": "ja", "zho": "zh", "pol": "pl", "tur": "tr", "swe": "sv", "dan": "da",
    "nor": "no", "fin": "fi", "ces": "cs", "ell": "el", "heb": "he", "hin": "hi",
    "ukr": "uk", "ron": "ro", "slv": "sl", "hrv": "hr", "srp": "sr", "bul": "bg",
    "vie": "vi", "tha": "th", "ind": "id", "msa": "ms", "fas": "fa", "hun": "hu",
}


def norm_lang(lang: str | None) -> str | None:
    """Normaliza el idioma a ISO 639-1 de 2 letras ('pt-BR' -> 'pt', 'spa' -> 'es').

    Devuelve None si no se puede normalizar (los feeds filtran por 'es','pt','en'...).
    """
    if not lang:
        return None
    l = lang.strip().lower().split("-")[0]
    if len(l) == 3:
        l = _ISO639_2_TO_1.get(l, l)
    if len(l) != 2 or not l.isalpha():
        return None
    return l