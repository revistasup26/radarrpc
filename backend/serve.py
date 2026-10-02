"""Entrypoint de despliegue (Render / VPS Docker).

Lee el puerto de la plataforma ($PORT) y arranca uvicorn escuchando en todas las
interfaces. No requiere que exista la base de datos: si falta, se inicializa vacía
y el cron la irá poblando.
"""
from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT") or os.environ.get("RADAR_PORT") or "8000")
    uvicorn.run("radar.api.main:app", host="0.0.0.0", port=port, workers=1)
