"""Capa SQLite: esquema, upserts y consultas del catálogo Radar RPC."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .normalize import norm, norm_lang

_SCHEMA = """
CREATE TABLE IF NOT EXISTS journals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    issn_print    TEXT,
    issn_online   TEXT,
    country       TEXT,
    source        TEXT NOT NULL DEFAULT 'seed',
    collection    TEXT,
    subject_areas TEXT,
    auto_discovered INTEGER DEFAULT 0,
    last_harvest  TEXT,
    UNIQUE(title)
);
CREATE INDEX IF NOT EXISTS idx_journals_issn_print  ON journals(issn_print);
CREATE INDEX IF NOT EXISTS idx_journals_issn_online ON journals(issn_online);

CREATE TABLE IF NOT EXISTS articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doi           TEXT UNIQUE,
    title         TEXT NOT NULL,
    title_alt     TEXT,
    abstract      TEXT,
    keywords      TEXT,
    authors       TEXT,
    journal_id    INTEGER,
    journal_title TEXT,
    issn          TEXT,
    volume        TEXT,
    issue         TEXT,
    pages         TEXT,
    year          INTEGER,
    pub_date      TEXT,
    lang          TEXT,
    url           TEXT,
    source        TEXT NOT NULL,
    source_id     TEXT,
    access        TEXT DEFAULT 'unknown',
    cited_by      INTEGER DEFAULT 0,
    openalex_id   TEXT,
    referenced_ids TEXT,
    is_rpc        INTEGER DEFAULT 0,
    cites_rpc     INTEGER DEFAULT 0,
    created_at    TEXT,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_pubdate ON articles(pub_date);
CREATE INDEX IF NOT EXISTS idx_articles_year    ON articles(year);
CREATE INDEX IF NOT EXISTS idx_articles_doi     ON articles(doi);
CREATE INDEX IF NOT EXISTS idx_articles_journal ON articles(journal_id);

CREATE TABLE IF NOT EXISTS harvest_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT NOT NULL,
    started_at     TEXT,
    finished_at    TEXT,
    status         TEXT,
    articles_found INTEGER,
    articles_new   INTEGER,
    notes          TEXT
);

CREATE TABLE IF NOT EXISTS keywords_flat (
    kw      TEXT PRIMARY KEY,
    norm_kw TEXT,
    n       INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_keywords_flat_n  ON keywords_flat(n);
CREATE INDEX IF NOT EXISTS idx_articles_cited   ON articles(cited_by DESC, pub_date DESC);

CREATE TABLE IF NOT EXISTS watch_keywords (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    label        TEXT,
    keywords     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    last_seen_id INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS author_stats (
    author_key     TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    first_pub_date TEXT,
    last_pub_date  TEXT,
    n              INTEGER DEFAULT 0,
    journals       TEXT
);
CREATE INDEX IF NOT EXISTS idx_author_stats_first ON author_stats(first_pub_date);
CREATE INDEX IF NOT EXISTS idx_author_stats_n ON author_stats(n);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    # Migraciones incrementales (base existente sin columnas nuevas)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
    if "cited_by" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN cited_by INTEGER DEFAULT 0")
    for col, ddl in (
        ("openalex_id", "TEXT"),
        ("referenced_ids", "TEXT"),
        ("is_rpc", "INTEGER DEFAULT 0"),
        ("cites_rpc", "INTEGER DEFAULT 0"),
    ):
        if col not in cols:
            try:
                conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {ddl}")
            except sqlite3.OperationalError:
                pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_rpc ON articles(is_rpc, cites_rpc)")
    except sqlite3.OperationalError:
        pass
    # Migración: norm_kw en keywords_flat para autocompletado acentuado (DB-4)
    kf_cols = {r[1] for r in conn.execute("PRAGMA table_info(keywords_flat)").fetchall()}
    if "norm_kw" not in kf_cols:
        try:
            conn.execute("ALTER TABLE keywords_flat ADD COLUMN norm_kw TEXT")
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_keywords_flat_norm ON keywords_flat(norm_kw)")
        has_nulls = conn.execute("SELECT 1 FROM keywords_flat WHERE norm_kw IS NULL LIMIT 1").fetchone()
        if has_nulls:
            rows = conn.execute("SELECT kw FROM keywords_flat WHERE norm_kw IS NULL").fetchall()
            for r in rows:
                conn.execute("UPDATE keywords_flat SET norm_kw = ? WHERE kw = ?", (norm(r["kw"]), r["kw"]))
    except Exception:
        pass
    # FTS5 para autocompletado (opcional: si el binario de sqlite no lo incluye, no romper)
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS keywords_fts USING fts5(kw)")
    except sqlite3.OperationalError:
        pass
    conn.commit()


# ---------------------------------------------------------------- journals
def upsert_journal(conn: sqlite3.Connection, j: dict) -> int:
    cur = conn.execute(
        """INSERT INTO journals (title, issn_print, issn_online, country, source, collection, subject_areas, auto_discovered, last_harvest)
           VALUES (:title, :issn_print, :issn_online, :country, :source, :collection, :subject_areas, :auto_discovered, :last_harvest)
           ON CONFLICT(title) DO UPDATE SET
             issn_print    = COALESCE(excluded.issn_print, journals.issn_print),
             issn_online   = COALESCE(excluded.issn_online, journals.issn_online),
             country       = COALESCE(excluded.country, journals.country),
             collection    = COALESCE(excluded.collection, journals.collection),
             subject_areas = COALESCE(excluded.subject_areas, journals.subject_areas),
             source        = journals.source
           RETURNING id""",
        {
            "title": j["title"],
            "issn_print": j.get("issn_print"),
            "issn_online": j.get("issn_online"),
            "country": j.get("country"),
            "source": j.get("source", "seed"),
            "collection": j.get("collection"),
            "subject_areas": json.dumps(j.get("subject_areas") or [], ensure_ascii=False),
            "auto_discovered": 1 if j.get("auto_discovered") else 0,
            "last_harvest": j.get("last_harvest"),
        },
    )
    row = cur.fetchone()
    # Si la revista descubierta tiene colección, vincularla también a revistas existentes por ISSN
    coll = j.get("collection")
    if coll:
        for issn in (j.get("issn_print"), j.get("issn_online")):
            if issn:
                conn.execute(
                    """UPDATE journals SET collection = ?
                       WHERE (issn_print = ? OR issn_online = ?) AND collection IS NULL""",
                    (coll, issn, issn),
                )
    conn.commit()
    return row["id"] if row else None


def all_journals(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM journals ORDER BY title").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["subject_areas"] = json.loads(d.get("subject_areas") or "[]")
        except json.JSONDecodeError:
            d["subject_areas"] = []
        out.append(d)
    return out


def journals_with_issn(conn: sqlite3.Connection) -> list[dict]:
    return [
        j
        for j in all_journals(conn)
        if j.get("issn_print") or j.get("issn_online")
    ]


# ---------------------------------------------------------------- articles
def _detect_rpc(a: dict) -> int:
    if a.get("is_rpc"):
        return 1
    from .conversation import is_rpc_article
    return 1 if is_rpc_article(a) else 0


def upsert_article(conn: sqlite3.Connection, a: dict) -> tuple[str, int]:
    """Inserta o actualiza por DOI. Devuelve (status, id). El idioma se normaliza a ISO 639-1."""
    ts = now_iso()
    lang = norm_lang(a.get("lang"))
    refs = a.get("referenced_ids") or []
    if isinstance(refs, str):
        refs_json = refs
    else:
        refs_json = json.dumps(refs, ensure_ascii=False)
    cur = conn.execute(
        """INSERT INTO articles (doi, title, title_alt, abstract, keywords, authors, journal_id,
                                 journal_title, issn, volume, issue, pages, year, pub_date, lang,
                                 url, source, source_id, access, cited_by, openalex_id, referenced_ids,
                                 is_rpc, cites_rpc, created_at, updated_at)
           VALUES (:doi, :title, :title_alt, :abstract, :keywords, :authors, :journal_id,
                   :journal_title, :issn, :volume, :issue, :pages, :year, :pub_date, :lang,
                   :url, :source, :source_id, :access, :cited_by, :openalex_id, :referenced_ids,
                   :is_rpc, :cites_rpc, :created_at, :updated_at)
           ON CONFLICT(doi) DO UPDATE SET
             title        = excluded.title,
             title_alt    = excluded.title_alt,
             abstract     = excluded.abstract,
             keywords     = excluded.keywords,
             authors      = excluded.authors,
             journal_id   = excluded.journal_id,
             journal_title= excluded.journal_title,
             issn         = excluded.issn,
             volume       = excluded.volume,
             issue        = excluded.issue,
             pages        = excluded.pages,
             year         = excluded.year,
             pub_date     = excluded.pub_date,
             lang         = excluded.lang,
             url          = excluded.url,
             access       = excluded.access,
             cited_by     = COALESCE(excluded.cited_by, articles.cited_by),
             openalex_id  = COALESCE(excluded.openalex_id, articles.openalex_id),
             referenced_ids = CASE
                 WHEN excluded.referenced_ids IS NOT NULL AND excluded.referenced_ids != '[]'
                 THEN excluded.referenced_ids ELSE articles.referenced_ids END,
             is_rpc       = MAX(excluded.is_rpc, articles.is_rpc),
             cites_rpc    = MAX(excluded.cites_rpc, articles.cites_rpc),
             updated_at   = excluded.updated_at
           RETURNING id, (updated_at <> created_at) AS was_update""",
        {
            "doi": a.get("doi"),
            "title": a["title"],
            "title_alt": a.get("title_alt"),
            "abstract": a.get("abstract"),
            "keywords": json.dumps(a.get("keywords") or [], ensure_ascii=False),
            "authors": json.dumps(a.get("authors") or [], ensure_ascii=False),
            "journal_id": a.get("journal_id"),
            "journal_title": a.get("journal_title"),
            "issn": a.get("issn"),
            "volume": a.get("volume"),
            "issue": a.get("issue"),
            "pages": a.get("pages"),
            "year": a.get("year"),
            "pub_date": a.get("pub_date"),
            "lang": lang,
            "url": a.get("url"),
            "source": a["source"],
            "source_id": a.get("source_id"),
            "access": a.get("access", "unknown"),
            "cited_by": a.get("cited_by"),
            "openalex_id": a.get("openalex_id"),
            "referenced_ids": refs_json,
            "is_rpc": _detect_rpc(a),
            "cites_rpc": int(a.get("cites_rpc") or 0),
            "created_at": ts,
            "updated_at": ts,
        },
    )
    row = cur.fetchone()
    conn.commit()
    was_update = bool(row and row["was_update"]) if row else False
    return ("updated" if was_update else "new", row["id"] if row else None)


def _row_to_article(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("keywords", "authors", "referenced_ids"):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except (json.JSONDecodeError, TypeError):
            d[k] = []
    d["is_rpc"] = int(d.get("is_rpc") or 0)
    d["cites_rpc"] = int(d.get("cites_rpc") or 0)
    return d


def get_article(conn: sqlite3.Connection, doi: str) -> dict | None:
    r = conn.execute("SELECT * FROM articles WHERE doi = ?", (doi,)).fetchone()
    return _row_to_article(r) if r else None


def count_articles(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()["n"]


def count_journals(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM journals").fetchone()["n"]


def stats(conn: sqlite3.Connection) -> dict:
    by_source = {
        r["source"]: r["n"]
        for r in conn.execute("SELECT source, COUNT(*) AS n FROM articles GROUP BY source").fetchall()
    }
    rpc_n = conn.execute("SELECT COUNT(*) AS n FROM articles WHERE is_rpc = 1").fetchone()["n"]
    cites_n = conn.execute("SELECT COUNT(*) AS n FROM articles WHERE cites_rpc = 1").fetchone()["n"]
    return {
        "articles": count_articles(conn),
        "journals": count_journals(conn),
        "by_source": by_source,
        "rpc_articles": rpc_n,
        "cites_rpc": cites_n,
    }


def load_rpc_articles(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM articles WHERE is_rpc = 1").fetchall()
    return [_row_to_article(r) for r in rows]


def rebuild_rpc_signals(conn: sqlite3.Connection) -> dict:
    """Marca el corpus RPC y las citas hacia él a partir de referenced_ids (OpenAlex y Crossref)."""
    from .conversation import strip_oaid

    conn.execute(
        """UPDATE articles SET is_rpc = 1
           WHERE replace(replace(ifnull(issn,''), '-', ''), ' ', '') LIKE ?
              OR (lower(ifnull(journal_title,'')) LIKE '%panamericana%'
                  AND lower(ifnull(journal_title,'')) LIKE '%comunic%')
              OR lower(ifnull(doi,'')) LIKE ?""",
        (f"%{config.RPC_ISSN.replace('-', '')}%", f"{config.RPC_DOI_PREFIX.lower()}%"),
    )
    ids = {
        strip_oaid(r["openalex_id"] or r["source_id"])
        for r in conn.execute(
            "SELECT openalex_id, source_id, source FROM articles WHERE is_rpc = 1"
        )
        if (r["openalex_id"] or (r["source"] == "openalex" and r["source_id"]))
    }
    ids.discard("")

    rpc_dois = {
        (r["doi"] or "").strip().lower()
        for r in conn.execute("SELECT doi FROM articles WHERE is_rpc = 1 AND doi IS NOT NULL").fetchall()
    }
    rpc_dois.discard("")
    prefix = config.RPC_DOI_PREFIX.lower()

    marked = 0
    rows = conn.execute(
        "SELECT id, referenced_ids FROM articles WHERE is_rpc = 0 AND referenced_ids IS NOT NULL"
    ).fetchall()
    for r in rows:
        try:
            refs = json.loads(r["referenced_ids"] or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        matches_oa = bool(ids and {strip_oaid(x) for x in refs} & ids)
        matches_doi = any(
            isinstance(x, str) and (x.strip().lower() in rpc_dois or x.strip().lower().startswith(prefix))
            for x in refs
        )
        if matches_oa or matches_doi:
            conn.execute("UPDATE articles SET cites_rpc = 1 WHERE id = ?", (r["id"],))
            marked += 1
    conn.commit()
    rpc_n = conn.execute("SELECT COUNT(*) AS n FROM articles WHERE is_rpc = 1").fetchone()["n"]
    return {"rpc_articles": rpc_n, "cites_rpc": marked}


def rebuild_keywords(conn: sqlite3.Connection) -> None:
    """Reconstruye keywords_flat y el índice FTS5 desde los artículos.

    Se invoca al final de cada cosecha; es barato (tabla << 50k filas).
    """
    conn.execute("DELETE FROM keywords_flat")
    try:
        conn.execute("DELETE FROM keywords_fts")
    except sqlite3.OperationalError:
        pass
    counts: dict[str, int] = {}
    rows = conn.execute("SELECT keywords FROM articles WHERE keywords IS NOT NULL").fetchall()
    for r in rows:
        try:
            kws = json.loads(r["keywords"])
        except (json.JSONDecodeError, TypeError):
            continue
        for kw in kws:
            if isinstance(kw, dict):
                kw = kw.get("k", "")
            kw = str(kw).strip()
            if kw:
                counts[kw] = counts.get(kw, 0) + 1
    conn.executemany(
        "INSERT INTO keywords_flat (kw, norm_kw, n) VALUES (?, ?, ?)",
        ((k, norm(k), v) for k, v in counts.items()),
    )
    try:
        conn.executemany("INSERT INTO keywords_fts (kw) VALUES (?)", ((k,) for k in counts))
    except sqlite3.OperationalError:
        pass
    conn.commit()


def suggest_keywords(conn: sqlite3.Connection, q: str, limit: int = 12) -> list[str]:
    """Autocompletado: FTS5 con prefijo; si FTS no está disponible, LIKE por frecuencia."""
    qn = norm(q)
    if not qn:
        return []
    if " " in qn:
        rows = conn.execute(
            "SELECT kw FROM keywords_flat WHERE norm_kw LIKE ? ORDER BY n DESC, kw LIMIT ?",
            (f"%{qn}%", limit),
        ).fetchall()
        return [r["kw"] for r in rows]
    # Prefijo simple (el término ya está normalizado: alfanumérico + espacios)
    try:
        term = qn.replace('"', '""')
        rows = conn.execute(
            "SELECT kw FROM keywords_fts WHERE keywords_fts MATCH ? ORDER BY rank LIMIT ?",
            (f'"{term}"*', limit),
        ).fetchall()
        if rows:            # FTS tiene datos: devolver; si vacío, caer al LIKE fallback
            return [r["kw"] for r in rows]
    except sqlite3.OperationalError:
        pass
    rows = conn.execute(
        "SELECT kw FROM keywords_flat WHERE norm_kw LIKE ? ORDER BY n DESC, kw LIMIT ?",
        (f"{qn}%", limit),
    ).fetchall()
    return [r["kw"] for r in rows]


# ---------------------------------------------------------------- author stats (emergentes)
def rebuild_author_stats(conn: sqlite3.Connection) -> None:
    """Reconstruye autorías agregadas (primera/última publicación, nº de artículos).

    Señal de autor 'emergente': primera publicación en el catálogo reciente + ≥2 artículos.
    """
    conn.execute("DELETE FROM author_stats")
    rows = conn.execute("SELECT pub_date, year, authors, journal_title FROM articles").fetchall()
    stats: dict[str, dict] = {}
    for r in rows:
        try:
            authors = json.loads(r["authors"])
        except (json.JSONDecodeError, TypeError):
            continue
        pd = r["pub_date"] or (f"{r['year']}-01-01" if r["year"] else "")
        for au in authors:
            if not isinstance(au, dict):
                continue
            given = str(au.get("given") or "").strip()
            family = str(au.get("family") or "").strip()
            if not (given or family):
                continue
            key = norm(f"{family} {given}")
            s = stats.setdefault(key, {
                "name": f"{given} {family}".strip()[:200],
                "first": None, "last": None, "n": 0, "journals": set(),
            })
            if pd:
                s["first"] = pd if (s["first"] is None or pd < s["first"]) else s["first"]
                s["last"] = pd if (s["last"] is None or pd > s["last"]) else s["last"]
            s["n"] += 1
            if r["journal_title"]:
                s["journals"].add(r["journal_title"])
    for key, s in stats.items():
        conn.execute(
            "INSERT INTO author_stats (author_key, name, first_pub_date, last_pub_date, n, journals)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (key, s["name"], s["first"], s["last"], s["n"],
             json.dumps(sorted(s["journals"])[:12], ensure_ascii=False)),
        )
    conn.commit()


# ---------------------------------------------------------------- watch (keywords ancladas)
def watch_list(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM watch_keywords ORDER BY created_at DESC, id DESC").fetchall()
    return [dict(r) for r in rows]


def watch_create(conn: sqlite3.Connection, keywords: str, label: str | None = None) -> dict:
    """Crea un ancla. last_seen_id = último artículo existente: solo contarán los NUEVOS."""
    from .matching import parse_keywords

    kws = parse_keywords(keywords)
    if not kws:
        raise ValueError("keywords vacías tras parsear")
    canonical = ", ".join(kws)
    max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM articles").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO watch_keywords (label, keywords, created_at, last_seen_id) VALUES (?, ?, ?, ?)",
        (label or canonical, canonical, now_iso(), max_id),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM watch_keywords WHERE id = ?", (cur.lastrowid,)).fetchone())


def watch_delete(conn: sqlite3.Connection, wid: int) -> bool:
    cur = conn.execute("DELETE FROM watch_keywords WHERE id = ?", (wid,))
    conn.commit()
    return cur.rowcount > 0


def _watch_candidates(conn: sqlite3.Connection, w: dict) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM articles WHERE id > ? ORDER BY id DESC LIMIT 800",
        (w["last_seen_id"],),
    ).fetchall()
    return [_row_to_article(r) for r in rows]


def watch_new_articles(conn: sqlite3.Connection, w: dict, limit: int = 20) -> list[dict]:
    """Artículos nuevos desde la última revisión que coinciden con las keywords del ancla."""
    from .matching import parse_keywords, rank_articles

    kws = parse_keywords(w.get("keywords") or "")
    if not kws:
        return []
    ranked = rank_articles(_watch_candidates(conn, w), kws)
    return [a for a in ranked if a["match_score"] > 0][:limit]


def watch_new_count(conn: sqlite3.Connection, w: dict) -> int:
    """Conteo de artículos nuevos para el ancla. Early-exit si no hay candidatos (BUG-NEW-3)."""
    has_new = conn.execute(
        "SELECT 1 FROM articles WHERE id > ? LIMIT 1", (w["last_seen_id"],)
    ).fetchone()
    if not has_new:
        return 0
    return len(watch_new_articles(conn, w, limit=800))


def watch_mark_seen(conn: sqlite3.Connection, wid: int) -> None:
    max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM articles").fetchone()[0]
    conn.execute("UPDATE watch_keywords SET last_seen_id = ? WHERE id = ?", (max_id, wid))
    conn.commit()


def watch_total(conn: sqlite3.Connection) -> dict:
    """Resumen para notificaciones: total de nuevas por ancla."""
    pins = []
    total = 0
    for w in watch_list(conn):
        n = watch_new_count(conn, w)
        total += n
        pins.append({"id": w["id"], "label": w["label"], "keywords": w["keywords"], "new": n})
    return {"total": total, "pins": pins}


def row_to_article(r) -> dict:
    """Alias público de _row_to_article (sin guion bajo) para uso en api/db internos."""
    return _row_to_article(r)


# ---------------------------------------------------------------- harvest log
def log_harvest(conn: sqlite3.Connection, source: str, status: str,
                found: int = 0, new: int = 0, notes: str = "") -> None:
    conn.execute(
        """INSERT INTO harvest_log (source, started_at, finished_at, status, articles_found, articles_new, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source, now_iso(), now_iso(), status, found, new, notes),
    )
    conn.commit()


def last_harvest(conn: sqlite3.Connection, source: str) -> dict | None:
    r = conn.execute(
        "SELECT * FROM harvest_log WHERE source = ? ORDER BY id DESC LIMIT 1", (source,)
    ).fetchone()
    return dict(r) if r else None