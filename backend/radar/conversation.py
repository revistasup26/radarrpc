"""Conversación con RPC: citas al corpus, encaje con el CFP y solapamiento temático."""
from __future__ import annotations

from functools import lru_cache

from . import config
from .matching import match_article
from .normalize import norm

STOP = {
    "para", "como", "este", "esta", "estos", "estas", "desde", "entre", "sobre",
    "hasta", "donde", "cuando", "porque", "desde", "hacia", "segun", "ante",
    "bajo", "tras", "mediante", "durante", "contra", "aunque", "tambien",
    "desde", "todos", "todas", "otro", "otra", "otros", "otras", "mismo",
    "misma", "cada", "muy", "mas", "menos", "pero", "sino", "cual", "cuales",
    "cuya", "cuyo", "esto", "eso", "aqui", "alli", "asi", "then", "with",
    "from", "that", "this", "these", "those", "which", "their", "have", "been",
    "were", "will", "into", "about", "through", "after", "before", "between",
    "without", "within", "among", "there", "where", "when", "what", "than",
    "them", "they", "said", "also", "more", "some", "such", "only", "other",
    "over", "both", "most", "into", "una", "uno", "del", "las", "los", "por",
    "con", "que", "the", "and", "for", "are", "not", "was", "his", "her",
    "its", "our", "can", "has", "had", "did", "who", "how", "why", "any",
    "all", "out", "new", "use", "using", "used", "based", "study", "paper",
    "article", "analisis", "estudio", "articulo", "revista", "comunicacion",
    "communication", "media", "social", "research",
}

_ISSN_COMPACT = config.RPC_ISSN.replace("-", "")


def strip_oaid(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.strip().replace("https://openalex.org/", "").upper()


def is_rpc_article(art: dict) -> bool:
    if art.get("is_rpc"):
        return True
    issn = (art.get("issn") or "").replace("-", "").replace(" ", "")
    if _ISSN_COMPACT and _ISSN_COMPACT in issn:
        return True
    doi = (art.get("doi") or "").lower()
    if doi.startswith(config.RPC_DOI_PREFIX.lower()):
        return True
    jt = norm(art.get("journal_title"))
    return "panamericana" in jt and "comunicacion" in jt


def _kw_strings(art: dict) -> list[str]:
    out = []
    for k in art.get("keywords") or []:
        if isinstance(k, str):
            out.append(k)
        elif isinstance(k, dict):
            out.append(str(k.get("k") or k.get("display_name") or ""))
    return [x for x in out if x]


def article_tokens(art: dict) -> set[str]:
    blob = " ".join([
        art.get("title") or "",
        " ".join(_kw_strings(art)),
        (art.get("abstract") or "")[:900],
    ])
    return {t for t in norm(blob).split() if len(t) > 3 and t not in STOP}


def _axis_tokens() -> set[str]:
    blob = " ".join(config.EDITORIAL_AXES + config.CURRENT_CFP["keywords"])
    return {t for t in norm(blob).split() if len(t) > 3 and t not in STOP}


def build_profile(rpc_articles: list[dict]) -> dict:
    """Perfil temático del corpus RPC (+ ejes editoriales y CFP como red de seguridad)."""
    oaids: set[str] = set()
    dois: set[str] = set()
    freq: dict[str, int] = {}
    for art in rpc_articles:
        raw_oa = art.get("openalex_id") or (art.get("source_id") if art.get("source") == "openalex" else None)
        oid = strip_oaid(raw_oa)
        if oid:
            oaids.add(oid)
        if art.get("doi"):
            dois.add(art["doi"].strip().lower())
        for t in article_tokens(art):
            freq[t] = freq.get(t, 0) + 1
    top = {t for t, n in freq.items() if n >= 2}
    if len(top) < 40:
        top |= {t for t, n in sorted(freq.items(), key=lambda kv: -kv[1])[:80]}
    top |= _axis_tokens()
    return {
        "openalex_ids": oaids,
        "dois": dois,
        "tokens": top,
        "n_works": len(rpc_articles),
        "cfp": config.CURRENT_CFP,
    }


@lru_cache(maxsize=1)
def _fallback_profile() -> dict:
    return {
        "openalex_ids": frozenset(),
        "dois": frozenset(),
        "tokens": frozenset(_axis_tokens()),
        "n_works": 0,
        "cfp": config.CURRENT_CFP,
    }


def fallback_profile() -> dict:
    p = _fallback_profile()
    return {
        "openalex_ids": set(p["openalex_ids"]),
        "dois": set(p["dois"]),
        "tokens": set(p["tokens"]),
        "n_works": 0,
        "cfp": config.CURRENT_CFP,
    }


def _cites_rpc(art: dict, profile: dict) -> bool:
    if art.get("cites_rpc"):
        return True
    refs = art.get("referenced_ids") or []
    if not refs or not profile.get("openalex_ids"):
        return False
    return bool({strip_oaid(x) for x in refs} & profile["openalex_ids"])


def score_article(art: dict, profile: dict) -> dict:
    """Señales de conversación con RPC. No usa keywords del usuario."""
    cfp_kw = list(profile.get("cfp", config.CURRENT_CFP).get("keywords") or [])
    cfp_m = match_article(art, cfp_kw) if cfp_kw else {"score": 0, "matched": []}
    axis_m = match_article(art, config.EDITORIAL_AXES)
    toks = article_tokens(art)
    inter = toks & (profile.get("tokens") or set())
    overlap_n = len(inter)
    overlap = (overlap_n / max(len(toks), 1)) if toks else 0.0
    cites = _cites_rpc(art, profile)
    home = is_rpc_article(art)

    score = 0
    if cites:
        score += 50
    score += min(30, int(cfp_m["score"]))
    score += min(18, int(axis_m["score"] * 0.6))
    score += min(40, overlap_n * 3)
    if overlap >= 0.18:
        score += 8
    if home:
        score = 0

    return {
        "cites_rpc": cites,
        "is_rpc": home,
        "cfp_score": int(cfp_m["score"]),
        "cfp_matched": cfp_m.get("matched") or [],
        "axis_score": int(axis_m["score"]),
        "overlap": round(overlap, 3),
        "overlap_n": overlap_n,
        "conversation_score": score,
    }


def why_labels(sig: dict, lang: str = "es") -> list[str]:
    cfp = config.CURRENT_CFP
    cfp_title = cfp["title_en"] if lang == "en" else cfp["title_es"]
    out: list[str] = []
    if sig.get("cites_rpc"):
        out.append(
            "Cites Revista Panamericana de Comunicación"
            if lang == "en"
            else "Cita artículos de la Revista Panamericana de Comunicación"
        )
    if sig.get("cfp_score", 0) > 0:
        out.append(
            f"Fits the current CFP: {cfp_title}"
            if lang == "en"
            else f"Encaja con el CFP vigente: {cfp_title}"
        )
    elif sig.get("axis_score", 0) > 0:
        out.append(
            "Matches the journal’s editorial scope"
            if lang == "en"
            else "Encaja con la línea editorial de RPC"
        )
    if sig.get("overlap_n", 0) >= 4 and not sig.get("cites_rpc"):
        n = sig["overlap_n"]
        out.append(
            f"In conversation with the RPC corpus ({n} thematic matches)"
            if lang == "en"
            else f"Dialoga con el corpus de RPC ({n} coincidencias temáticas)"
        )
    return out[:3]


def _date_key(pub_date: str | None) -> int:
    if not pub_date:
        return 0
    d = str(pub_date).replace("-", "")[:8]
    return int(d) if d.isdigit() else 0


def rank_conversation(articles: list[dict], profile: dict, mode: str = "conversation") -> list[dict]:
    enriched = []
    for a in articles:
        if is_rpc_article(a):
            continue
        sig = score_article(a, profile)
        if sig["conversation_score"] <= 0:
            continue
        if mode == "cfp" and sig["cfp_score"] <= 0:
            continue
        enriched.append({**a, "conversation": sig})
    if mode == "cfp":
        key = lambda a: (-(a["conversation"]["cfp_score"] or 0), -_date_key(a.get("pub_date")))
    elif mode == "latest":
        key = lambda a: (-_date_key(a.get("pub_date")), a.get("doi") or "")
    else:
        key = lambda a: (
            -(a["conversation"]["conversation_score"] or 0),
            -(1 if a["conversation"]["cites_rpc"] else 0),
            -_date_key(a.get("pub_date")),
        )
    enriched.sort(key=key)
    return enriched
