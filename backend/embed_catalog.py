"""Script para calcular embeddings BGE-M3 de todo el catálogo local."""
import sys
import os
from pathlib import Path
import json
import sqlite3
import numpy as np

# Añadir el backend al path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from radar import db, vector_store, config

def main():
    print("Conectando a la base de datos...")
    conn = db.connect()
    
    print("Cargando modelo BAAI/bge-m3...")
    model = vector_store.get_model()
    
    print("Obteniendo artículos...")
    articles = conn.execute("SELECT doi, title, abstract FROM articles WHERE doi IS NOT NULL").fetchall()
    conn.close()
    
    if not articles:
        print("No hay artículos en la base de datos.")
        return
        
    print(f"Calculando embeddings para {len(articles)} artículos. Esto puede tomar unos minutos...")
    
    dois = []
    texts = []
    for row in articles:
        dois.append(row["doi"])
        # Unir título y resumen
        t = (row["title"] or "").strip()
        a = (row["abstract"] or "").strip()
        text = f"{t} {a}".strip()
        texts.append(text)
    
    # Calcular embeddings (bge-m3 usa normalize_embeddings para que el dot product sea la similitud del coseno)
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    
    # Guardar en data/
    npz_path = vector_store._get_npz_path()
    dois_path = vector_store._get_dois_path()
    
    np.savez_compressed(npz_path, embeddings=embeddings)
    with open(dois_path, "w", encoding="utf-8") as f:
        json.dump(dois, f)
        
    print(f"✅ ¡Embeddings guardados exitosamente!")
    print(f"Vectores: {npz_path}")
    print(f"DOIs: {dois_path}")

if __name__ == "__main__":
    main()
