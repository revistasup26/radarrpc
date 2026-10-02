"""Lanzador local de Radar RPC: dos instancias de uvicorn en el puerto 8000
(IPv4 127.0.0.1 + IPv6 ::1) para que 'localhost' funcione SIEMPRE en el navegador,
independientemente de si Windows resuelve localhost a ::1 o a 127.0.0.1.

Uso:  .venv\\Scripts\\python.exe run_server.py   (Ctrl+C para detener)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = HERE / ".venv" / "Scripts" / "python.exe"


def main() -> int:
    if not PY.exists():
        print("[ERROR] No existe el entorno virtual en .venv. Ejecuta antes:")
        print("        uv venv .venv")
        print("        uv pip install --python .venv fastapi \"uvicorn[standard]\" apscheduler httpx")
        return 1

    port = str(os.environ.get("RADAR_PORT") or (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].isdigit() else "8922"))

    procs = []
    for host in ("127.0.0.1", "::1"):
        p = subprocess.Popen(
            [str(PY), "-m", "uvicorn", "radar.api.main:app", "--host", host, "--port", port, "--reload"],
            cwd=HERE,
        )
        procs.append(p)

    print("=" * 56)
    print(f"  RADAR RPC — servidor local (IPv4 + IPv6) en puerto {port}")
    print(f"  PWA:     http://localhost:{port}/app/")
    print(f"  Widget:  http://localhost:{port}/widget")
    print(f"  API:     http://localhost:{port}/api/health")
    print(f"  Docs:    http://localhost:{port}/docs")
    print("  Ctrl+C para detener.")
    print("=" * 56)

    try:
        while True:
            time.sleep(1)
            for p in procs:
                if p.poll() is not None:
                    print(f"[ERROR] Un servidor terminó con código {p.returncode}")
                    for other in procs:
                        other.terminate()
                    return 1
    except KeyboardInterrupt:
        print("\nDeteniendo Radar RPC…")
        for p in procs:
            p.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())