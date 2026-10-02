"""Matching por keywords: transparencia bibliométrica (por qué se seleccionó cada artículo).

Reglas jerárquicas:
1. Coincidencia exacta de frase (y variantes directas ES/PT como 'comunicación social' ⇄ 'comunicação social'):
   máxima puntuación (peso * 3).
2. Coincidencia de todos los términos en el mismo campo (ej. 'comunicación' y 'social' en el título):
   alta puntuación (peso * 2).
3. Coincidencia de término individual (insensible a acentos/género/número y variantes ES/PT):
   puntuación estándar (peso * 2).
4. Coincidencia distribuida en el artículo (un término en título y otro en resumen):
   puntuación de contexto (peso 1).
5. Tolerancia a erratas leves en la consulta (ej. 'comunciación' -> 'comunicación').
"""
from __future__ import annotations

import re
from functools import lru_cache

from .normalize import edit_distance, norm, word_variants

# Peso base de cada campo donde aparece la keyword
FIELD_WEIGHTS = {"title": 3, "keywords": 2, "abstract": 1}
FIELD_LABELS = {
    "title": "Título",
    "keywords": "Palabras clave del artículo",
    "abstract": "Resumen",
}

_KEYWORD_SPLIT = re.compile(r"[,;|]+|\n")
_DASH_SEP = re.compile(r"\s+[-–—]\s+")

# Vocabulario de términos frecuentes en Comunicación para corrección rápida de erratas
COMMON_VOCAB = {
    "comunicacion", "comunicacao", "comunicaciones", "comunicacoes",
    "periodismo", "jornalismo", "periodista", "periodistas", "jornalista", "jornalistas",
    "desinformacion", "desinformacao", "investigacion", "investigacao",
    "cientifica", "cientifico", "cientificas", "cientificos",
    "politica", "politico", "politicas", "politicos",
    "social", "sociales", "sociais", "digital", "digitales", "digitais",
    "inteligencia", "artificial", "medios", "mediatica", "mediatico",
    "audiovisual", "publicidad", "propaganda", "audiencias",
    "narrativa", "narrativas", "discurso", "discursos", "divulgacion", "divulgacao",
    "intercultural", "comunitaria", "comunitario", "organizacional", "institucional",
    "cultura", "cultural", "culturales", "educacion", "educacao", "tecnologia", "tecnologias",
}


@lru_cache(maxsize=512)
def correct_word(word: str) -> str:
    """Corrige una palabra de la búsqueda si presenta una errata evidente."""
    wn = norm(word)
    if not wn or wn in COMMON_VOCAB:
        return wn
    if len(wn) >= 6:
        c0 = wn[0]
        max_d = 2 if len(wn) >= 8 else 1
        best = None
        min_d = 99
        for c in COMMON_VOCAB:
            if c[0] == c0 and abs(len(c) - len(wn)) <= max_d:
                d = edit_distance(wn, c)
                if d < min_d:
                    min_d = d
                    best = c
        if best and min_d <= max_d:
            return best
    return wn


def parse_keywords(raw: str | None) -> list[str]:
    """Divide la entrada del usuario en keywords individuales.

    Acepta separadores: coma, punto y coma, barra, salto de línea y guiones con
    espacios ('a - b' / 'a – b'). Deduplica (insensible a acentos/mayúsculas).
    """
    if not raw:
        return []
    parts: list[str] = []
    for chunk in _KEYWORD_SPLIT.split(raw):
        for piece in _DASH_SEP.split(chunk):
            piece = piece.strip().strip("-–—").strip()
            if piece:
                parts.append(piece)
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        k = norm(p)
        if k and k not in seen:
            seen.add(k)
            out.append(p)
    return out


def prepare_query_plan(keywords: list[str]) -> list[dict]:
    """Precompila las variantes lingüísticas y de erratas para evaluar artículos velozmente."""
    plan = []
    for raw_kw in keywords:
        nk = norm(raw_kw)
        if not nk:
            continue
        raw_tokens = nk.split()
        corrected_tokens = [correct_word(t) for t in raw_tokens]
        is_phrase = len(raw_tokens) > 1

        phrase_variants = []
        if is_phrase:
            phrase_variants.append(" ".join(corrected_tokens))
            if "comunicacion" in corrected_tokens:
                phrase_variants.append(" ".join(["comunicacao" if t == "comunicacion" else t for t in corrected_tokens]))
            if "comunicacao" in corrected_tokens:
                phrase_variants.append(" ".join(["comunicacion" if t == "comunicacao" else t for t in corrected_tokens]))
            if any("cientific" in t for t in corrected_tokens):
                phrase_variants.append(" ".join([t.replace("cientifica", "cientifico") for t in corrected_tokens]))

        token_var_sets = [word_variants(correct_word(t)) for t in raw_tokens]
        plan.append({
            "raw_kw": raw_kw,
            "is_phrase": is_phrase,
            "phrase_variants": phrase_variants,
            "token_var_sets": token_var_sets,
        })
    return plan


def _score_article_with_plan(art: dict, query_plan: list[dict]) -> dict:
    """Evalúa un artículo frente a un plan de consulta precompilado."""
    haystacks = {
        "title": norm(art.get("title")),
        "keywords": " ".join(
            norm(k) if isinstance(k, str) else norm(k.get("k", ""))
            for k in (art.get("keywords") or [])
        ),
        "abstract": norm(art.get("abstract")),
    }
    field_token_sets = {f: set(text.split()) for f, text in haystacks.items()}

    matched: list[dict] = []
    total_score = 0

    for item in query_plan:
        raw_kw = item["raw_kw"]
        is_phrase = item["is_phrase"]
        phrase_variants = item["phrase_variants"]
        token_var_sets = item["token_var_sets"]

        kw_matched = False
        # 1. Coincidencia exacta de frase o variante directa ES/PT (máxima prioridad)
        for field, text in haystacks.items():
            if not text:
                continue
            if is_phrase and any(pv in text for pv in phrase_variants):
                w = FIELD_WEIGHTS[field] * 3
                total_score += w
                matched.append({"keyword": raw_kw, "field": field, "weight": w})
                kw_matched = True
                break

        if kw_matched:
            continue

        # 2. Todos los términos presentes en el mismo campo
        if is_phrase:
            for field in ("title", "keywords", "abstract"):
                tok_set = field_token_sets[field]
                if all(bool(tok_set & var_set) for var_set in token_var_sets):
                    w = FIELD_WEIGHTS[field] * 2
                    total_score += w
                    matched.append({"keyword": raw_kw, "field": field, "weight": w})
                    kw_matched = True
                    break

        if kw_matched:
            continue

        # 3. Consulta de un solo término
        if not is_phrase:
            var_set = token_var_sets[0]
            for field in ("title", "keywords", "abstract"):
                tok_set = field_token_sets[field]
                if tok_set & var_set:
                    w = FIELD_WEIGHTS[field] * 2
                    total_score += w
                    matched.append({"keyword": raw_kw, "field": field, "weight": w})
                    kw_matched = True
                    break

        if kw_matched:
            continue

        # 4. Todos los términos distribuidos en el artículo (título + resumen + keywords)
        if is_phrase:
            all_toks = field_token_sets["title"] | field_token_sets["keywords"] | field_token_sets["abstract"]
            if all(bool(all_toks & var_set) for var_set in token_var_sets):
                w = 1
                total_score += w
                matched.append({"keyword": raw_kw, "field": "abstract", "weight": w})
                kw_matched = True

    return {"score": total_score, "matched": matched}


def match_article(art: dict, keywords: list[str]) -> dict:
    """Compara un artículo contra la lista de keywords del usuario.

    Devuelve {'score': int, 'matched': [{'keyword', 'field', 'weight'}]}.
    """
    plan = prepare_query_plan(keywords)
    return _score_article_with_plan(art, plan)


def _date_key(pub_date: str | None) -> int:
    """Clave numérica de fecha ISO (YYYY-MM-DD) para ordenar; sin fecha = 0."""
    if not pub_date:
        return 0
    d = pub_date.replace("-", "")
    return int(d) if d.isdigit() else 0


def rank_articles(articles: list[dict], keywords: list[str]) -> list[dict]:
    """Enriquece cada artículo con su explicación y lo ordena por score + fecha."""
    plan = prepare_query_plan(keywords)
    enriched = []
    for a in articles:
        m = _score_article_with_plan(a, plan)
        enriched.append({**a, "match_score": m["score"], "matched": m["matched"]})
    enriched.sort(
        key=lambda a: (
            -(a["match_score"] or 0),
            -_date_key(a.get("pub_date")),   # a igual score, el más reciente primero
            a.get("doi") or "",
        )
    )
    return enriched