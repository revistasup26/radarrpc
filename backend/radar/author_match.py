"""Motor de Afinidad Autoral / 'Match Académico' (Conexión de Pares en Comunicación).

Permite a los autores de Revista Panamericana de Comunicación (o cualquier investigador)
identificar a sus pares en las otras 144 revistas iberoamericanas que publican en la misma línea,
mostrando afinidad temática, artículos clave y puntos de diálogo conceptual.
"""
from __future__ import annotations

import logging
import sqlite3
from . import config, db
from .conversation import STOP
from .normalize import norm, word_variants
from .topics import classify_article_fields

log = logging.getLogger("radar.author_match")

ACADEMIC_STOP = STOP | {
    "estudio", "analisis", "articulo", "investigacion", "resultados", "metodologia",
    "objetivo", "conclusiones", "datos", "autores", "trabajo", "presenta", "plantea",
    "study", "analysis", "paper", "research", "results", "methodology", "objective",
    "conclusions", "data", "authors", "work", "presents", "approaches", "review",
    "literature", "output", "systematic", "field", "fields", "studies", "growing",
    "toward", "towards", "between", "through", "within", "without", "across",
    "estudo", "artigo", "pesquisa", "dados", "autores", "trabalho", "apresenta",
    "first", "second", "third", "based", "using", "used", "which", "their", "there",
    "about", "into", "also", "more", "most", "some", "such", "only", "other", "both",
}


def _clean_tokens(art: dict) -> set[str]:
    kws = " ".join(
        k if isinstance(k, str) else str(k.get("k") or k.get("display_name") or "")
        for k in (art.get("keywords") or [])
    )
    text = f"{art.get('title') or ''} {kws} {art.get('abstract') or ''}"
    return {t for t in norm(text).split() if len(t) > 3 and t not in ACADEMIC_STOP}


def list_rpc_articles(conn: sqlite3.Connection) -> list[dict]:
    """Lista todos los artículos de RPC con autores formateados para facilitar la selección."""
    rows = conn.execute(
        """SELECT * FROM articles 
           WHERE journal_title LIKE ? OR issn LIKE ? OR doi LIKE ?
           ORDER BY pub_date DESC, id DESC""",
        (f"%{config.RPC_TITLE}%", f"%{config.RPC_ISSN}%", f"%{config.RPC_DOI_PREFIX}%")
    ).fetchall()
    out = []
    for r in rows:
        a = db._row_to_article(r)
        aus = [f"{au.get('given','')} {au.get('family','')}".strip()
               for au in (a.get("authors") or []) if isinstance(au, dict)]
        out.append({
            "id": a["id"],
            "title": a["title"],
            "year": a.get("year"),
            "pub_date": a.get("pub_date"),
            "doi": a.get("doi"),
            "authors": aus,
            "authors_str": ", ".join(aus) if aus else "Autoría RPC",
            "journal": a.get("journal_title") or config.RPC_TITLE,
        })
    return out


def find_author_matches(
    conn: sqlite3.Connection,
    article_id: int | None = None,
    author_name: str | None = None,
    topic_query: str | None = None,
    limit: int = 6
) -> dict:
    """Busca autores de otras revistas con alta afinidad temática (Match Académico)."""
    target_art = None
    target_tokens: set[str] = set()
    source_label = ""
    author_source_name = author_name or ""

    if article_id:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if row:
            target_art = db._row_to_article(row)
            target_tokens = _clean_tokens(target_art)
            source_label = target_art.get("title", "")
            if not author_source_name and target_art.get("authors"):
                aus = [f"{au.get('given','')} {au.get('family','')}".strip()
                       for au in target_art.get("authors") if isinstance(au, dict)]
                author_source_name = ", ".join(aus[:2])
    elif author_name:
        rows = conn.execute(
            "SELECT * FROM articles WHERE authors LIKE ? ORDER BY pub_date DESC LIMIT 5",
            (f"%{author_name}%",)
        ).fetchall()
        for r in rows:
            target_tokens.update(_clean_tokens(db._row_to_article(r)))
        source_label = f"Producción de {author_name}"
    elif topic_query:
        target_tokens = {t for t in norm(topic_query).split() if len(t) > 3 and t not in ACADEMIC_STOP}
        source_label = f"Línea de investigación: {topic_query}"

    if not target_tokens:
        # Fallback de seguridad
        target_tokens = {"comunicacion", "medios", "tecnologia", "periodismo"}
        source_label = "Líneas de investigación en Comunicación"

    # Campos temáticos del target
    target_fields = classify_article_fields(target_art) if target_art else []
    target_field_names = [f["name"] for f in target_fields]

    # Excluir a los propios autores del artículo target
    exclude_authors = set()
    if target_art and target_art.get("authors"):
        for au in target_art.get("authors"):
            if isinstance(au, dict):
                exclude_authors.add(norm(f"{au.get('given','')} {au.get('family','')}"))
    if author_source_name:
        exclude_authors.add(norm(author_source_name))

    # Query semántico (BGE-M3). Si no está disponible, se continúa sin candidatos
    # semánticos (el despliegue ligero para el widget de OJS no incluye numpy/torch).
    semantic_query = ""
    if topic_query:
        semantic_query = topic_query
    elif target_art:
        semantic_query = f"{target_art.get('title', '')} {target_art.get('abstract', '')}"
    elif author_source_name:
        semantic_query = " ".join(target_tokens)

    semantic_results = []
    if semantic_query and len(semantic_query) > 5:
        try:
            from . import vector_store
            semantic_results = vector_store.search(semantic_query, top_k=60)
        except Exception as e:  # noqa: BLE001
            log.info("Búsqueda semántica no disponible: %s", e)
            semantic_results = []

    author_candidates = {}

    if semantic_results:
        dois = [r["doi"] for r in semantic_results]
        placeholders = ",".join("?" for _ in dois)
        # Buscar en DB, excluyendo RPC
        other_rows = conn.execute(
            f"""SELECT * FROM articles 
               WHERE doi IN ({placeholders}) 
               AND journal_title NOT LIKE ? AND issn NOT LIKE ?""",
            dois + [f"%{config.RPC_TITLE}%", f"%{config.RPC_ISSN}%"]
        ).fetchall()

        row_map = {r["doi"]: r for r in other_rows}

        for res in semantic_results:
            if res["doi"] not in row_map:
                continue

            art = db._row_to_article(row_map[res["doi"]])

            # Base score basado en similitud semántica (ej. 0.8 * 100)
            base_score = res["match_score"] * 100

            # Boost si comparten descriptores fuertes
            toks = _clean_tokens(art)
            common = target_tokens & toks
            for special_term in ("tiktok", "desinformacion", "algoritmos", "inteligencia", "transmedia", "podcast", "polarizacion", "violencia"):
                if special_term in common:
                    base_score += 15

            aus = art.get("authors") or []
            for au in aus:
                    if not isinstance(au, dict):
                        continue
                    name = f"{au.get('given','')} {au.get('family','')}".strip()
                    if not name or norm(name) in exclude_authors:
                        continue

                    if name not in author_candidates:
                        author_candidates[name] = {
                            "name": name,
                            "raw_score": 0,
                            "journal": art.get("journal_title") or "Revista de Comunicación",
                            "articles": [],
                            "common_tokens": set(),
                        }

                    author_candidates[name]["raw_score"] += base_score
                    author_candidates[name]["common_tokens"].update(common)
                    if len(author_candidates[name]["articles"]) < 2:
                        author_candidates[name]["articles"].append({
                            "title": art.get("title"),
                            "year": art.get("year"),
                            "journal": art.get("journal_title"),
                            "doi": art.get("doi"),
                        })

    sorted_authors = sorted(author_candidates.values(), key=lambda x: -x["raw_score"])
    matches = []

    for c in sorted_authors[:limit]:
        # Calcular afinidad relativa (máximo 98%, mínimo 65% para que sea atractivo)
        affinity = min(98, max(68, int(55 + c["raw_score"] * 0.4)))
        contact_pts = [t.capitalize() for t in list(c["common_tokens"])[:5]]

        matches.append({
            "name": c["name"],
            "affinity": affinity,
            "journal": c["journal"],
            "shared_concepts": contact_pts,
            "articles": c["articles"],
            "match_rationale": (
                f"Comparte foco investigativo en {', '.join(contact_pts[:3])}. "
                f"Publica activamente en «{c['journal']}»."
            ),
        })

    return {
        "status": "ok",
        "source": {
            "label": source_label,
            "author": author_source_name,
            "fields": target_field_names,
        },
        "count": len(matches),
        "matches": matches,
    }
