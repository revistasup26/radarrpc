"""Orquestador de cosecha: semilla -> descubrimiento SciELO -> Crossref -> SciELO -> Redalyc."""
from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx

from .. import config, db
from . import crossref, openalex, redalyc, scielo
from .journals_seed import SEED_JOURNALS

log = logging.getLogger("radar.pipeline")


def _new_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": config.USER_AGENT},
        follow_redirects=True,
        timeout=45.0,
    )


def _maybe_rebuild_embeddings(conn) -> dict | None:
    """Tras cosechar, reconstruye el índice semántico si el modelo está disponible.

    Es opcional y tolera fallos: sin sentence-transformers (p. ej. despliegue ligero
    para el widget de OJS) el radar sigue funcionando con búsqueda léxica.
    """
    try:
        from .. import vector_store
    except Exception as e:  # noqa: BLE001
        log.info("Embeddings: vector_store no disponible (%s).", e)
        return None
    try:
        return vector_store.build_index(conn)
    except Exception as e:  # noqa: BLE001
        log.warning("Embeddings: no se pudo reconstruir el índice (%s).", e)
        return None


def run_pipeline(sources: list[str] | None = None,
                 days: int | None = None,
                 max_articles: int | None = None,
                 collections: list[str] | None = None,
                 http: httpx.Client | None = None) -> dict:
    sources = [s.strip().lower() for s in (sources or ["seed", "scielo", "crossref", "openalex", "redalyc"])]
    days = days or config.DEFAULT_DAYS
    limit = max_articles or config.MAX_ARTICLES_PER_RUN
    today = date.today()
    date_from = (today - timedelta(days=days)).isoformat()
    date_to = today.isoformat()

    conn = db.connect()
    db.init_db(conn)
    close_http = http is None
    http = http or _new_client()

    report: dict = {"date_from": date_from, "date_to": date_to, "sources": {}, "journals": 0, "articles": 0, "new": 0}

    try:
        # 1) Red semilla curada
        if "seed" in sources:
            n = 0
            for j in SEED_JOURNALS:
                db.upsert_journal(conn, {**j, "source": "seed", "auto_discovered": False})
                n += 1
            report["sources"]["seed"] = {"status": "ok", "journals_seeded": n}
            log.info("Semilla: %d revistas", n)

        # 1b) Corpus canónico de RPC (toda la vida de la revista, no la ventana corta)
        try:
            rpc_found = 0
            for a in openalex.harvest_issns(http, [config.RPC_ISSN], config.RPC_FOUNDED, max_articles=400):
                row = a.db_row()
                row["is_rpc"] = 1
                if row.get("doi") or row.get("openalex_id"):
                    db.upsert_article(conn, row)
                    rpc_found += 1
            for a in crossref.harvest_by_issn(http, config.RPC_ISSN, config.RPC_FOUNDED, max_articles=400):
                row = a.db_row()
                row["is_rpc"] = 1
                if row.get("doi"):
                    db.upsert_article(conn, row)
                    rpc_found += 1
            report["sources"]["rpc_corpus"] = {"status": "ok", "found": rpc_found}
            log.info("Corpus RPC: %d registros", rpc_found)
        except Exception as e:
            report["sources"]["rpc_corpus"] = {"status": "error", "detail": str(e)}
            log.warning("Corpus RPC falló: %s", e)

        journals = db.all_journals(conn)

        # 2) Descubrimiento automático de revistas de Comunicación en SciELO
        if "scielo" in sources:
            try:
                discovered = scielo.discover_journals(http, collections=collections)
                for j in discovered:
                    db.upsert_journal(conn, j)
                report["sources"]["scielo_discovery"] = {"status": "ok", "journals_found": len(discovered)}
                journals = db.all_journals(conn)
                log.info("Descubrimiento SciELO: %d revistas de Comunicación", len(discovered))
            except Exception as e:
                report["sources"]["scielo_discovery"] = {"status": "error", "detail": str(e)}
                log.warning("Descubrimiento SciELO falló: %s", e)

        budget = max(20, limit // max(len(journals), 1))

        # 3) Crossref por ISSN (impreso + online)
        if "crossref" in sources:
            found = new = 0
            errors = 0
            for j in journals:
                issns = scielo._valid_issns([x for x in (j.get("issn_print"), j.get("issn_online")) if x])
                for issn in issns:
                    try:
                        arts = crossref.harvest_by_issn(http, issn, date_from,
                                                        max_articles=min(budget, 60))
                        for a in arts:
                            status, _ = db.upsert_article(conn, a.db_row())
                            found += 1
                            if status == "new":
                                new += 1
                    except Exception as e:
                        errors += 1
                        log.warning("Crossref %s: %s", issn, e)
            db.log_harvest(conn, "crossref", "ok", found, new,
                           f"revistas={len(journals)} errores={errors}")
            report["sources"]["crossref"] = {"status": "ok", "found": found, "new": new, "errors": errors}
            log.info("Crossref: %d artículos (%d nuevos)", found, new)

        # 4) OpenAlex por ISSN (antes que SciELO: si hay DOI duplicado,
        #    gana el registro rico de SciELO con keywords/abstract por idioma)
        if "openalex" in sources:
            found = new = 0
            errors = 0
            issn_set: set[str] = set()
            for j in journals:
                for x in (j.get("issn_print"), j.get("issn_online")):
                    if x:
                        issn_set.add(x)
            batches = [sorted(issn_set)[i:i + 8] for i in range(0, len(issn_set), 8)]
            for batch in batches:
                try:
                    arts = openalex.harvest_issns(http, batch, date_from,
                                                  max_articles=min(budget * 2, 150))
                    for a in arts:
                        if not a.doi:
                            continue
                        status, _ = db.upsert_article(conn, a.db_row())
                        found += 1
                        if status == "new":
                            new += 1
                except Exception as e:
                    errors += 1
                    log.warning("OpenAlex lote: %s", e)
            db.log_harvest(conn, "openalex", "ok", found, new,
                           f"revistas={len(journals)} lotes={len(batches)} errores={errors}")
            report["sources"]["openalex"] = {"status": "ok", "found": found, "new": new, "errors": errors}
            log.info("OpenAlex: %d artículos (%d nuevos)", found, new)

        # 5) SciELO por revista (ISSN + colección), solo artículos de investigación
        if "scielo" in sources:
            found = new = 0
            errors = 0
            sci_journals = [
                j for j in journals
                if j.get("collection") and scielo._valid_issns([x for x in (j.get("issn_print"), j.get("issn_online")) if x])
            ]
            for j in sci_journals:
                issn = scielo._valid_issns([x for x in (j.get("issn_print"), j.get("issn_online")) if x])[0]
                try:
                    arts = scielo.harvest_journal(http, j["collection"], issn,
                                                  date_from, date_to,
                                                  max_articles=min(budget, 15))
                    for a in arts:
                        # Dedupe para artículos sin DOI: (source, source_id) ya existe
                        if a.source_id:
                            exists = conn.execute(
                                "SELECT 1 FROM articles WHERE source = 'scielo' AND source_id = ?",
                                (a.source_id,),
                            ).fetchone()
                            if exists:
                                continue
                        status, _ = db.upsert_article(conn, a.db_row())
                        found += 1
                        if status == "new":
                            new += 1
                except Exception as e:
                    errors += 1
                    log.warning("SciELO %s/%s: %s", j.get("collection"), issn, e)
            db.log_harvest(conn, "scielo", "ok", found, new,
                           f"revistas={len(sci_journals)} errores={errors}")
            report["sources"]["scielo"] = {"status": "ok", "found": found, "new": new, "errors": errors}
            log.info("SciELO: %d artículos (%d nuevos)", found, new)

        # 6) Redalyc vía OAI-PMH (UAEMex / Redalyc)
        if "redalyc" in sources:
            try:
                journal_issns = []
                for j in journals:
                    for i in (j.get("issn_print"), j.get("issn_online")):
                        if i and scielo._ISSN_RE.match(i.strip()):
                            journal_issns.append(i.strip().upper())
                arts = redalyc.harvest(http, date_from, max_articles=min(limit, 300), sets=journal_issns[:50])
                found = new = 0
                for a in arts:
                    if not a.doi and not a.source_id:
                        continue
                    if not a.doi and a.source_id:
                        exists = conn.execute(
                            "SELECT 1 FROM articles WHERE source = 'redalyc' AND source_id = ?",
                            (a.source_id,),
                        ).fetchone()
                        if exists:
                            continue
                    status, _ = db.upsert_article(conn, a.db_row())
                    found += 1
                    if status == "new":
                        new += 1
                db.log_harvest(conn, "redalyc", "ok", found, new, f"artículos={found} nuevos={new}")
                report["sources"]["redalyc"] = {"status": "ok", "found": found, "new": new}
            except Exception as e:
                db.log_harvest(conn, "redalyc", "error", 0, 0, str(e))
                report["sources"]["redalyc"] = {"status": "error", "detail": str(e)}
                log.warning("Redalyc: %s", e)

        st = db.stats(conn)
        report["journals"] = st["journals"]
        report["articles"] = st["articles"]
        report["by_source"] = st["by_source"]
        # Índices derivados: keywords (autocompletado) y autorías (emergentes)
        db.rebuild_keywords(conn)
        db.rebuild_author_stats(conn)
        report["rpc_signals"] = db.rebuild_rpc_signals(conn)
        # Índice semántico (opcional; se omite en despliegues ligeros sin sentence-transformers)
        emb = _maybe_rebuild_embeddings(conn)
        if emb is not None:
            report["embeddings"] = emb
        return report
    finally:
        if close_http:
            http.close()
        conn.close()