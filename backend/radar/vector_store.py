"""Módulo de almacenamiento vectorial y búsqueda semántica con BAAI/bge-m3."""
import os
import json
import logging
import sqlite3
import numpy as np
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

from . import config

log = logging.getLogger("radar.vector_store")

_model = None
_embeddings = None
_dois = []

def get_model():
    global _model
    if _model is None:
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers no está instalado.")
        log.info("Cargando modelo BAAI/bge-m3... (esto puede tardar unos segundos)")
        _model = SentenceTransformer('BAAI/bge-m3')
    return _model

def _get_npz_path() -> Path:
    return config.DATA_DIR / "embeddings.npz"

def _get_dois_path() -> Path:
    return config.DATA_DIR / "embeddings_dois.json"

def load_index():
    """Carga los vectores y los DOIs en memoria."""
    global _embeddings, _dois
    npz_path = _get_npz_path()
    dois_path = _get_dois_path()
    
    if npz_path.exists() and dois_path.exists():
        data = np.load(npz_path)
        _embeddings = data['embeddings']
        with open(dois_path, 'r', encoding='utf-8') as f:
            _dois = json.load(f)
        log.info(f"Índice vectorial cargado: {_embeddings.shape[0]} artículos.")
    else:
        _embeddings = None
        _dois = []
        log.warning("No hay índice vectorial. Ejecuta embed_catalog.py primero.")

def reset_index() -> None:
    """Libera el índice en memoria (p. ej. tras una cosecha que regeneró los embeddings)."""
    global _embeddings, _dois, _model
    _embeddings = None
    _dois = []
    _model = None


def embed_texts(texts: list[str]):
    """Codifica una lista de textos con bge-m3. Devuelve una matriz normalizada (N x D)."""
    model = get_model()
    return model.encode([t or "" for t in texts], normalize_embeddings=True)


def build_index(conn: sqlite3.Connection, batch_size: int = 64) -> dict:
    """(Re)construye embeddings.npz + embeddings_dois.json a partir de la tabla articles.

    Permite que el harvester actualice el índice dentro del contenedor, sin depender
    de ejecutar embed_catalog.py por separado.
    """
    global _embeddings, _dois
    rows = conn.execute("SELECT doi, title, abstract, keywords FROM articles").fetchall()
    items = []
    for r in rows:
        doi = (r["doi"] or "").strip()
        if not doi:
            continue
        kw = r["keywords"] or ""
        blob = f"{r['title'] or ''}. {kw}. {(r['abstract'] or '')[:700]}".strip()
        items.append((doi, blob))
    if not items:
        reset_index()
        return {"count": 0, "path": None}

    dois = [d for d, _ in items]
    texts = [b for _, b in items]
    model = get_model()
    vecs = []
    for i in range(0, len(texts), batch_size):
        vecs.append(model.encode(texts[i:i + batch_size], normalize_embeddings=True))
    embeddings = np.vstack(vecs).astype("float32")

    np.savez_compressed(_get_npz_path(), embeddings=embeddings)
    with open(_get_dois_path(), "w", encoding="utf-8") as f:
        json.dump(dois, f, ensure_ascii=False)

    _embeddings = embeddings
    _dois = dois
    log.info("Índice vectorial reconstruido: %d artículos.", len(dois))
    return {"count": len(dois), "path": str(_get_npz_path())}


def search(query: str, top_k: int = 50) -> list[dict]:
    """
    Busca semánticamente el query en el índice.
    Devuelve lista de {"doi": str, "match_score": float}.
    """
    if _embeddings is None or len(_dois) == 0:
        load_index()
    if _embeddings is None or len(_dois) == 0:
        return []

    model = get_model()
    # Para bge-m3, simplemente podemos codificar la query.
    query_vec = model.encode([query], normalize_embeddings=True)[0]

    # Similitud de coseno (producto escalar si están normalizados)
    scores = np.dot(_embeddings, query_vec)

    # Ordenar índices de mayor a menor
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        results.append({
            "doi": _dois[idx],
            "match_score": float(scores[idx]),
            "matched": [{"keyword": "Búsqueda Semántica (BGE-M3)", "field": "semantic", "weight": float(scores[idx])}]
        })
    return results
