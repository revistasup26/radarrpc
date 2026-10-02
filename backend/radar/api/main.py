"""API REST de Radar RPC (FastAPI)."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import mimetypes
import threading

mimetypes.init()
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

from .. import config, db
from ..citations import citation_filename, format_citation
from ..conversation import (
    build_profile,
    fallback_profile,
    rank_conversation,
    score_article,
    why_labels,
)
from .. import author_match, socratic, topics
from ..matching import match_article, parse_keywords, rank_articles
from .scheduler import build_scheduler

log = logging.getLogger("radar.api")
class HarvestState:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "idle"
        self.started_at = None
        self.finished_at = None
        self.last_report = None
        self.error = None

    def get_dict(self):
        with self.lock:
            return {
                "status": self.status,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "last_report": self.last_report,
                "error": self.error
            }

_harvest_state = HarvestState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Arranque/cierre: init DB y scheduler opcional."""
    conn = db.connect()
    db.init_db(conn)
    db.rebuild_rpc_signals(conn)
    conn.close()
    
    # Intentar cargar el índice vectorial si existe
    try:
        from .. import vector_store
        vector_store.load_index()
    except Exception as e:
        log.warning(f"No se pudo cargar vector_store: {e}")
        
    sched = None
    if config.AUTO_HARVEST:
        sched = build_scheduler()
        sched.start()
        log.info("Scheduler automático iniciado (cada %dh)", config.HARVEST_INTERVAL_HOURS)
    try:
        yield
    finally:
        if sched:
            sched.shutdown(wait=False)


app = FastAPI(
    title="Radar RPC API",
    description="Radar de la Revista Panamericana de Comunicación.\n"
                "Filosofía: «No busques el paper. Deja que el paper te encuentre.»",
    version=config.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # TODO: Para el plugin OJS en producción, limitar esto a los orígenes del OJS
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- helpers
def _safe_doi(doi: str) -> str:
    return doi.strip().lower()


def _rpc_profile(conn) -> dict:
    arts = db.load_rpc_articles(conn)
    return build_profile(arts) if arts else fallback_profile()


def _widget_card(a: dict, lang: str) -> dict:
    conv = a.get("conversation") or {}
    aus = (a.get("authors") or [])
    names = []
    for au in aus:
        if isinstance(au, dict):
            names.append(f"{au.get('family') or ''} {au.get('given') or ''}".strip())
        elif au:
            names.append(str(au))
    names = [n for n in names if n]
    return {
        "title": a.get("title"),
        "url": a.get("url") or (f"https://doi.org/{a['doi']}" if a.get("doi") else None),
        "doi": a.get("doi"),
        "authors": names[:3],
        "journal_title": a.get("journal_title"),
        "year": a.get("year"),
        "pub_date": (a.get("pub_date") or "")[:10],
        "why": why_labels(conv, lang),
        "cites_rpc": bool(conv.get("cites_rpc")),
        "cfp_score": conv.get("cfp_score") or 0,
        "access": a.get("access"),
    }


def _query_articles(conn, days: int | None, langs: list[str], sources: list[str],
                    order: str = "pub_date", max_rows: int | None = None) -> list:
    sql = "SELECT * FROM articles WHERE 1=1"
    params: list = []
    if days:
        since = (date.today() - timedelta(days=days)).isoformat()
        sql += " AND pub_date >= ?"
        params.append(since)
    if langs:
        # Los artículos sin idioma declarado (p. ej. Crossref) se incluyen por defecto
        sql += f" AND (lang IN ({','.join('?' * len(langs))}) OR lang IS NULL)"
        params.extend(langs)
    if sources:
        sql += f" AND source IN ({','.join('?' * len(sources))})"
        params.extend(sources)
    sql += " ORDER BY " + ("cited_by DESC, pub_date DESC" if order == "cited" else "pub_date DESC")
    if max_rows:
        sql += f" LIMIT {int(max_rows)}"
    rows = conn.execute(sql, params).fetchall()
    return [db._row_to_article(r) for r in rows]


# ---------------------------------------------------------------- endpoints
@app.get("/")
def root():
    return RedirectResponse("/app/")


@app.get("/widget")
def widget_redirect():
    return RedirectResponse("/app/widget.html")


@app.get("/api/health")
def health():
    conn = db.connect()
    try:
        st = db.stats(conn)
        return {
            "status": "ok",
            "version": config.VERSION,
            "filosofia": "No busques el paper. Deja que el paper te encuentre.",
            "journal": config.RPC_TITLE,
            "stats": st,
        }
    finally:
        conn.close()


@app.get("/api/feed")
def feed(
    keywords: str = Query("", description="Keywords separadas por coma"),
    langs: str = Query("", description="Idiomas separados por coma: es,pt,en"),
    sources: str = Query("", description="Fuentes separadas por coma: scielo,crossref,openalex,redalyc"),
    limit: int = Query(5, ge=1, le=20),
    days: int = Query(1825, ge=1, le=3650),
    sort: str = Query("relevance", pattern="^(relevance|recent|cited)$",
                      description="relevance=score+prominencia, recent=más recientes, cited=más citados"),
    show_all: bool = Query(False, description="Ignorar keywords y devolver los más recientes"),
):
    conn = db.connect()
    try:
        kw_list = parse_keywords(keywords)
        lang_list = [l.strip().lower() for l in langs.split(",") if l.strip()]
        src_list = [s.strip().lower() for s in sources.split(",") if s.strip()]
        has_kw = bool(kw_list) and not show_all
        # Si hay keywords, evaluar todo el catálogo dentro de la ventana (sin corte artificial)
        max_rows = None if has_kw else 800
        arts = _query_articles(conn, days, lang_list, src_list, order=sort, max_rows=max_rows)
        if has_kw:
            from .. import vector_store
            ranked = []
            try:
                semantic_results = vector_store.search(" ".join(kw_list), top_k=100)
            except Exception as e:
                log.debug("Búsqueda semántica no disponible, usando coincidencia léxica: %s", e)
                semantic_results = []
            if semantic_results:
                score_map = {r["doi"]: r for r in semantic_results}
                for a in arts:
                    if a.get("doi") in score_map:
                        a["match_score"] = score_map[a["doi"]]["match_score"]
                        a["matched"] = score_map[a["doi"]]["matched"]
                        # Umbral mínimo de similitud para BGE M3
                        if a["match_score"] > 0.4:
                            ranked.append(a)
                if sort == "relevance":
                    ranked.sort(key=lambda x: x["match_score"], reverse=True)
            # Si la vía semántica no devuelve nada sobre el umbral, caer a matching léxico
            if not ranked:
                ranked = rank_articles(arts, kw_list)
                ranked = [a for a in ranked if a["match_score"] > 0]
        else:
            ranked = arts
            for a in ranked:
                a.setdefault("match_score", 0)
                a.setdefault("matched", [])
        # Jerarquización explícita (relevance ya está ordenado por rank_articles)
        if sort == "recent":
            ranked.sort(key=lambda a: (a.get("pub_date") or "", a.get("doi") or ""), reverse=True)
        elif sort == "cited":
            ranked.sort(key=lambda a: (a.get("cited_by") or 0, a.get("pub_date") or ""), reverse=True)
        ranked = ranked[:limit]
        profile = _rpc_profile(conn)
        for a in ranked:
            sig = score_article(a, profile)
            a["conversation"] = {**sig, "why": why_labels(sig, "es")}
            a["thematic_fields"] = topics.classify_article_fields(a)
            a.pop("referenced_ids", None)

        # Ayuda cuando no hay resultados: ¿existen en una ventana más amplia (sin filtros)?
        hints = None
        if not ranked and kw_list and days < 365:
            arts_year = _query_articles(conn, 365, [], [], order=sort, max_rows=None)
            counts = []
            for kw in kw_list:
                n = sum(1 for a in arts_year if match_article(a, [kw])["score"] > 0)
                counts.append({"keyword": kw, "count": n})
            hints = {"wider_window": {"days": 365, "keyword_counts": counts}}

        return {
            "query": {"keywords": kw_list, "langs": lang_list, "sources": src_list,
                      "days": days, "limit": limit, "sort": sort},
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "count": len(ranked),
            "hints": hints,
            "articles": ranked,
        }
    finally:
        conn.close()


@app.get("/api/articles/{doi:path}/citation")
def citation(doi: str, format: str = Query("apa", pattern="^(apa|bibtex|ris)$")):
    conn = db.connect()
    try:
        a = db.get_article(conn, _safe_doi(doi))
        if not a:
            raise HTTPException(404, "Artículo no encontrado")
        text = format_citation(a, format)
        fname = citation_filename(a, format)
        return Response(
            content=text,
            media_type={"apa": "text/plain; charset=utf-8",
                        "bibtex": "application/x-bibtex; charset=utf-8",
                        "ris": "application/x-research-info-systems; charset=utf-8"}[format],
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    finally:
        conn.close()


@app.get("/api/articles/{doi:path}")
def article(doi: str):
    """Metadatos completos del artículo en JSON (incluye keywords, autores y matched)."""
    conn = db.connect()
    try:
        a = db.get_article(conn, _safe_doi(doi))
        if not a:
            raise HTTPException(404, "Artículo no encontrado")
        return JSONResponse(a, media_type="application/json; charset=utf-8")
    finally:
        conn.close()


@app.get("/api/cfp")
def cfp():
    return {"journal": config.RPC_TITLE, "cfp": config.CURRENT_CFP, "axes": config.EDITORIAL_AXES}


@app.get("/api/widget")
def widget_feed(
    mode: str = Query("conversation", pattern="^(conversation|cfp|latest)$"),
    lang: str = Query("es", pattern="^(es|en)$"),
    limit: int = Query(5, ge=1, le=10),
    days: int = Query(365, ge=30, le=3650),
):
    """Payload compacto para el embed OJS: papers en conversación con RPC."""
    conn = db.connect()
    try:
        profile = _rpc_profile(conn)
        arts = _query_articles(conn, days, [], [], order="pub_date", max_rows=500)
        ranked = rank_conversation(arts, profile, mode=mode)[:limit]
        cfp = config.CURRENT_CFP
        return {
            "journal": config.RPC_TITLE,
            "mode": mode,
            "lang": lang,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cfp": {
                "title": cfp["title_en"] if lang == "en" else cfp["title_es"],
                "period": cfp["period_en"] if lang == "en" else cfp["period_es"],
                "url": cfp["url_en"] if lang == "en" else cfp["url"],
            },
            "submit_url": config.RPC_SUBMIT[lang],
            "home_url": f"{config.RPC_HOME}/{'en' if lang == 'en' else 'es'}",
            "radar_url": "/app/",
            "corpus": {"rpc_articles": profile.get("n_works") or 0},
            "count": len(ranked),
            "articles": [_widget_card(a, lang) for a in ranked],
        }
    finally:
        conn.close()


@app.get("/api/sources")
def sources_status():
    conn = db.connect()
    try:
        out = {}
        for s in ("scielo", "crossref", "openalex", "redalyc"):
            lh = db.last_harvest(conn, s)
            out[s] = lh or {"status": "never"}
        return {"sources": out}
    finally:
        conn.close()


@app.get("/api/journals")
def journals(q: str = "", limit: int = Query(50, le=500)):
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM journals WHERE title LIKE ? ORDER BY title LIMIT ?",
            (f"%{q}%", limit),
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            try:
                d["subject_areas"] = json.loads(d.get("subject_areas") or "[]")
            except json.JSONDecodeError:
                d["subject_areas"] = []
            out.append(d)
        return {"count": len(out), "journals": out}
    finally:
        conn.close()


@app.get("/api/stats")
def stats():
    conn = db.connect()
    try:
        st = db.stats(conn)
        by_source = {}
        for r in conn.execute("SELECT source, COUNT(*) n FROM journals GROUP BY source").fetchall():
            by_source[r["source"]] = r["n"]
        st["journals_by_source"] = by_source
        return st
    finally:
        conn.close()


@app.get("/api/suggest")
def suggest(q: str = "", limit: int = Query(12, le=30)):
    conn = db.connect()
    try:
        return {"keywords": db.suggest_keywords(conn, q, limit)}
    finally:
        conn.close()


@app.get("/api/authors")
def authors(sort: str = Query("new", pattern="^(new|emerging|active)$"),
            days: int = Query(365, ge=1, le=3650),
            limit: int = Query(10, ge=1, le=50)):
    """Autores: 'new' = primera publicación en la ventana; 'emerging' = nueva + ≥2 artículos;
    'active' = con más publicaciones en la ventana. Señales calculadas sobre el catálogo."""
    conn = db.connect()
    try:
        since = (date.today() - timedelta(days=days)).isoformat()
        if sort == "emerging":
            rows = conn.execute(
                """SELECT * FROM author_stats
                   WHERE first_pub_date >= ? AND n >= 2
                   ORDER BY first_pub_date DESC, n DESC LIMIT ?""",
                (since, limit),
            ).fetchall()
        elif sort == "active":
            rows = conn.execute(
                """SELECT * FROM author_stats
                   WHERE last_pub_date >= ? AND n >= 2
                   ORDER BY n DESC, last_pub_date DESC LIMIT ?""",
                (since, limit),
            ).fetchall()
        else:  # new
            rows = conn.execute(
                """SELECT * FROM author_stats
                   WHERE first_pub_date >= ?
                   ORDER BY first_pub_date DESC LIMIT ?""",
                (since, limit),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["journals"] = json.loads(d.get("journals") or "[]")
            except json.JSONDecodeError:
                d["journals"] = []
            out.append(d)
        return {"sort": sort, "days": days, "count": len(out), "authors": out}
    finally:
        conn.close()


# ---------------------------------------------------------------- campos y socrático
@app.get("/api/topics")
def topics_list():
    """Campos canónicos de conocimiento en Ciencias de la Comunicación."""
    return {"fields": topics.COMMUNICATION_FIELDS}


@app.post("/api/socratic/analyze")
def socratic_analyze(payload: dict = Body(...)):
    """Conduce un turno del diálogo socrático (multi-turno) con evaluación FINER."""
    inquiry = str(payload.get("inquiry") or "").strip()
    if not inquiry:
        raise HTTPException(422, "inquiry es obligatorio")
    history = payload.get("history") or []
    if not isinstance(history, list):
        history = []
    conn = db.connect()
    try:
        return socratic.analyze_inquiry(inquiry, conn, history=history)
    finally:
        conn.close()


@app.post("/api/socratic/concert")
def socratic_concert(payload: dict = Body(...)):
    """Concierta el horizonte de radar temático y opcionalmente lo ancla."""
    field_id = str(payload.get("field_id") or "").strip()
    inquiry = str(payload.get("inquiry") or "").strip()
    reflection = str(payload.get("reflection") or "").strip()
    finer = payload.get("finer") if isinstance(payload.get("finer"), dict) else None
    pin = bool(payload.get("pin", False))
    conn = db.connect()
    try:
        res = socratic.concert_radar(field_id, inquiry, reflection, conn, finer=finer)
        if pin and res.get("recommended_keywords"):
            w = db.watch_create(conn, res["recommended_keywords"], res["label"])
            res["pin"] = w
        return res
    finally:
        conn.close()


# ---------------------------------------------------------------- afinidad autoral (match académico)
@app.get("/api/rpc/articles")
def rpc_articles():
    """Lista los artículos publicados en RPC para selección rápida de autor."""
    conn = db.connect()
    try:
        articles = author_match.list_rpc_articles(conn)
        return {"count": len(articles), "articles": articles}
    finally:
        conn.close()


@app.get("/api/authors/match")
def author_matches(
    article_id: int | None = Query(None, description="ID de artículo de RPC para buscar pares"),
    author_name: str | None = Query(None, description="Nombre de autor de RPC"),
    topic: str | None = Query(None, description="Tema o línea de investigación"),
    limit: int = Query(6, ge=1, le=20)
):
    """Motor de Afinidad Autoral ('Match Académico / Tinder Científico')."""
    conn = db.connect()
    try:
        return author_match.find_author_matches(
            conn,
            article_id=article_id,
            author_name=author_name,
            topic_query=topic,
            limit=limit,
        )
    finally:
        conn.close()


# ---------------------------------------------------------------- anclas (watch)
@app.get("/api/watch")
def watch_list_endpoint():
    """Lista ligera de anclas guardadas sin cómputo de novedades (O(1)). Úsa esta ruta
    para renderizar la lista de anclas; usa /api/watch/total para los conteos."""
    conn = db.connect()
    try:
        return {"pins": db.watch_list(conn)}
    finally:
        conn.close()


@app.get("/api/watch/total")
def watch_total():
    """Anclas con conteo de publicaciones nuevas desde la última revisión.
    Más costoso que /api/watch; optimizado con early-exit por ancla."""
    conn = db.connect()
    try:
        return db.watch_total(conn)
    finally:
        conn.close()


@app.post("/api/watch")
def watch_create(payload: dict = Body(...)):
    keywords = str(payload.get("keywords") or "").strip()
    if not keywords:
        raise HTTPException(422, "keywords es obligatorio")
    label = str(payload.get("label") or "").strip() or keywords
    conn = db.connect()
    try:
        w = db.watch_create(conn, keywords, label)
        return w
    finally:
        conn.close()


@app.delete("/api/watch/{wid}")
def watch_delete(wid: int):
    conn = db.connect()
    try:
        if not db.watch_delete(conn, wid):
            raise HTTPException(404, "Ancla no encontrada")
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/watch/{wid}/new")
def watch_new(wid: int, mark: int = Query(0, ge=0, le=1),
              limit: int = Query(20, ge=1, le=50)):
    """Artículos nuevos para el ancla desde la última revisión (mark=1 la marca como vista)."""
    conn = db.connect()
    try:
        w = next((x for x in db.watch_list(conn) if x["id"] == wid), None)
        if not w:
            raise HTTPException(404, "Ancla no encontrada")
        articles = db.watch_new_articles(conn, w, limit=limit)
        if mark:
            db.watch_mark_seen(conn, wid)
        return {"id": wid, "label": w["label"], "keywords": w["keywords"],
                "count": len(articles), "articles": articles}
    finally:
        conn.close()


def _run_harvest_bg(sources: list[str], days: int):
    with _harvest_state.lock:
        _harvest_state.status = "running"
        _harvest_state.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _harvest_state.finished_at = None
        _harvest_state.last_report = None
        _harvest_state.error = None

    try:
        from ..harvester.pipeline import run_pipeline
        report = run_pipeline(sources=sources, days=days)
        with _harvest_state.lock:
            _harvest_state.status = "finished"
            _harvest_state.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            _harvest_state.last_report = report
    except Exception as e:
        log.exception("Error en cosecha asíncrona")
        with _harvest_state.lock:
            _harvest_state.status = "error"
            _harvest_state.error = str(e)
            _harvest_state.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.post("/api/harvest/run", status_code=202)
def run_harvest(background_tasks: BackgroundTasks, days: int = Query(90, ge=1), sources: str = "scielo,crossref"):
    with _harvest_state.lock:
        if _harvest_state.status == "running":
            raise HTTPException(409, "Ya hay una cosecha en curso")
        # Marcar preventivamente para que otros requests fallen inmediatamente
        _harvest_state.status = "running"

    src_list = [s.strip() for s in sources.split(",") if s.strip()]
    background_tasks.add_task(_run_harvest_bg, src_list, days)
    return {"status": "accepted", "message": "Cosecha iniciada en segundo plano"}


@app.get("/api/harvest/status")
def harvest_status():
    return _harvest_state.get_dict()


# ---------------------------------------------------------------- PWA estática
class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


if config.PWA_DIR.exists():
    app.mount("/app", NoCacheStaticFiles(directory=str(config.PWA_DIR), html=True), name="pwa")