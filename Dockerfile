# Radar RPC — imagen para API/PWA (widget OJS) + cosecha.
#
# ARG RADAR_HEAVY:
#   0 (default)  -> despliegue ligero: solo API/widget, SIN torch/BGE-M3.
#                   La búsqueda semántica se desactiva y se usa coincidencia léxica.
#   1            -> incluye sentence-transformers + torch (búsqueda semántica y
#                   reconstrucción de embeddings tras cada cosecha). Requiere ~2 GB+ RAM.
ARG RADAR_HEAVY=0

FROM python:3.11-slim

ARG RADAR_HEAVY=0
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RADAR_DATA_DIR=/data \
    RADAR_DB_PATH=/data/radar.db \
    RADAR_PWA_DIR=/app/pwa

WORKDIR /app

# Dependencias base (ligeras)
RUN pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]>=0.30" "apscheduler>=3.10" "httpx>=0.27"

# Dependencias pesadas opcionales (semántica)
RUN if [ "$RADAR_HEAVY" = "1" ]; then \
        pip install --no-cache-dir "sentence-transformers>=3.0" "numpy>=1.24" ; \
    fi

# Código
COPY backend/ /app/
COPY pwa/ /app/pwa/
COPY data/ /data/

EXPOSE 8000
CMD ["python", "serve.py"]
