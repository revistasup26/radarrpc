"""Configuración de Radar RPC (variables de entorno con valores por defecto)."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

DATA_DIR = Path(os.environ.get("RADAR_DATA_DIR", PROJECT_ROOT / "data"))
DB_PATH = Path(os.environ.get("RADAR_DB_PATH", DATA_DIR / "radar.db"))
PWA_DIR = Path(os.environ.get("RADAR_PWA_DIR", PROJECT_ROOT / "pwa"))

MAILTO = os.environ.get("RADAR_MAILTO", "rpc@up.edu.mx")
USER_AGENT = os.environ.get(
    "RADAR_USER_AGENT",
    f"RadarRPC/0.2 (Revista Panamericana de Comunicacion; contacto: {MAILTO})",
)

HARVEST_INTERVAL_HOURS = int(os.environ.get("RADAR_HARVEST_INTERVAL_HOURS", "6"))
AUTO_HARVEST = os.environ.get("RADAR_AUTO_HARVEST", "0") == "1"
DEFAULT_DAYS = int(os.environ.get("RADAR_DEFAULT_DAYS", "365"))
MAX_ARTICLES_PER_RUN = int(os.environ.get("RADAR_MAX_ARTICLES", "1500"))
REQUEST_DELAY = float(os.environ.get("RADAR_REQUEST_DELAY", "0.15"))

REDALYC_TOKEN = os.environ.get("REDALYC_TOKEN", "")

PORT = int(os.environ.get("RADAR_PORT", "8922"))

# --- LLM (local LM Studio u OpenAI-compatible remoto, p. ej. Groq) ---
# RADAR_LLM_URL apunta al endpoint /v1 del proveedor. Si no se define, se usa
# RADAR_LMSTUDIO_URL (compatibilidad). Para Groq:
#   RADAR_LLM_URL=https://api.groq.com/openai/v1
#   RADAR_LLM_API_KEY=gsk_...
#   RADAR_LLM_MODEL=llama-3.3-70b-versatile
LMSTUDIO_BASE_URL = os.environ.get("RADAR_LMSTUDIO_URL", "http://127.0.0.1:1234/v1")
LLM_URL = os.environ.get("RADAR_LLM_URL") or LMSTUDIO_BASE_URL
LLM_API_KEY = os.environ.get("RADAR_LLM_API_KEY", "")
LLM_MODEL = os.environ.get("RADAR_LLM_MODEL", "")
LMSTUDIO_TIMEOUT = float(os.environ.get("RADAR_LMSTUDIO_TIMEOUT", "120.0"))

VERSION = "0.2.0"

RPC_ISSN = "2683-2208"
RPC_TITLE = "Revista Panamericana de Comunicación"
RPC_DOI_PREFIX = "10.21555/rpc"
RPC_HOME = "https://revistas.up.edu.mx/rpc"
RPC_SUBMIT = {
    "es": "https://revistas.up.edu.mx/rpc/es/about/submissions",
    "en": "https://revistas.up.edu.mx/rpc/en/about/submissions",
}
RPC_FOUNDED = "2019-01-01"

CURRENT_CFP = {
    "id": "8.2-2026",
    "volume": "8",
    "issue": "2",
    "period_es": "julio–diciembre 2026",
    "period_en": "July–December 2026",
    "title_es": "Ecología de los Medios: El entorno tecnológico como cultura y extensión humana",
    "title_en": "Media Ecology: The technological environment as culture and human extension",
    "url": "https://revistas.up.edu.mx/rpc/es/announcement/view/38",
    "url_en": "https://revistas.up.edu.mx/rpc/en/announcement/view/38",
    "editors": [
        "Laura Trujillo-Liñán",
        "Octavio Islas",
        "Lance Strate",
        "Fernando Gutiérrez",
    ],
    "keywords": [
        "ecología de los medios",
        "media ecology",
        "entorno tecnológico",
        "extensión humana",
        "marshall mcluhan",
        "tecnología y cultura",
        "medio como mensaje",
        "ambiente mediático",
        "cultura tecnológica",
        "human extension",
        "technological environment",
        "media as environment",
    ],
}

EDITORIAL_AXES = [
    "comunicación política",
    "fotografía y ética",
    "narrativas televisivas",
    "ética y estética",
    "metodologías de investigación",
    "historia de la comunicación",
    "industria cinematográfica",
    "videojuegos",
    "ecología de los medios",
]
