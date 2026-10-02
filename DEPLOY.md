# Despliegue de Radar RPC (widget para OJS)

Este documento cubre las dos vías pedidas: **VPS con Docker** y **Render**.

El widget de OJS (`/app/embed.js` → `widget.html` → `/api/widget`) **no necesita IA ni
BGE-M3**: solo FastAPI + la base `radar.db`. Por eso el despliegue público puede ser
ligero (imagen sin torch, ~200 MB). La PWA de investigación (`/app/`) y el diálogo
socrático con IA siguen pensados para correr en local con LM Studio.

---

## 0. Qué se despliega

| Endpoint / ruta | Uso |
|---|---|
| `/app/embed.js` | script para incrustar en OJS |
| `/app/widget.html` | iframe del widget |
| `/api/widget` | datos del widget (conversación / CFP / recientes) |
| `/app/` | PWA completa |
| `/api/health` | healthcheck |

Variables de entorno relevantes:

| Variable | Valor sugerido | Nota |
|---|---|---|
| `PORT` | lo pone la plataforma (Render) | `serve.py` lo lee |
| `RADAR_DATA_DIR` | `/data` | carpeta persistente |
| `RADAR_DB_PATH` | `/data/radar.db` | base SQLite |
| `RADAR_PWA_DIR` | `/app/pwa` | ya fijada en el Dockerfile |
| `RADAR_AUTO_HARVEST` | `0` | la cosecha la hace el cron, no el proceso web |
| `RADAR_MAILTO` | `rpc@up.edu.mx` | polite pool de Crossref/OpenAlex |

---

## 1. VPS con Docker (recomendado)

### Requisitos
- Un VPS Linux (Hetzner/DigitalOcean, ~1 vCPU / 2 GB es suficiente en modo ligero).
- Docker + Docker Compose.
- Un dominio apuntando al VPS (p. ej. `radar.revistas.up.edu.mx`).

### Pasos
```bash
git clone <tu-repo> radar-obcc && cd radar-obcc

# 1) Arrancar la API/PWA
docker compose up -d --build

# 2) Primera cosecha (puebla /data/radar.db dentro del volumen)
docker compose run --rm harvester \
  sh -c "python -m radar.harvester.cli --days 365 --max-articles 2500"

# 3) Comprobar
curl http://127.0.0.1:8000/api/health
```

### Cosecha automática (cron del host)
```cron
0 */6 * * * cd /opt/radar-obcc && /usr/bin/docker compose run --rm harvester >> /var/log/radar-harvest.log 2>&1
```

### HTTPS con Caddy (proxy inverso con certificado automático)
```caddyfile
radar.revistas.up.edu.mx {
    reverse_proxy 127.0.0.1:8000
}
```

### Habilitar búsqueda semántica (opcional, +2 GB RAM)
En `docker-compose.yml` cambia `RADAR_HEAVY: "1"` y reconstruye:
```bash
docker compose build --no-cache && docker compose up -d
```
Recuerda que el contenedor de cosecha también deberá usar la imagen pesada para
regenerar embeddings (ya la usa, porque comparte `image: radar-rpc:latest`).

---

## 2. Render

### Opción A — Blueprint (recomendado)
1. Sube el repo a GitHub.
2. En Render: **New → Blueprint**, apunta al repo. Render lee `render.yaml` y crea:
   - Web Service Docker `radar-rpc` (con disco persistente `/data`).
   - Cron Job `radar-harvest` cada 6 h.
3. Define el secreto `RADAR_MAILTO` cuando lo pida.
4. Espera el primer deploy y revisa `https://<tu-servicio>.onrender.com/api/health`.

### Opción B — Manual
- **Web Service**: Docker, `Dockerfile` en la raíz, healthcheck `/api/health`.
  - Añade un **Persistent Disk** montado en `/data`.
  - Env: `RADAR_DATA_DIR=/data`, `RADAR_DB_PATH=/data/radar.db`, `RADAR_AUTO_HARVEST=0`.
- **Cron Job**: mismo Dockerfile; comando
  `python -m radar.harvester.cli --days 30 --max-articles 1200`;
  monta el **mismo** disco persistente en `/data`.

> Nota: si prefieres que el propio proceso web haga la cosecha (sin cron), pon
> `RADAR_AUTO_HARVEST=1` y el scheduler interno la lanzará cada 6 h. **No uses ambos**
> a la vez: dos procesos escribiendo el mismo SQLite puede bloquear la base.

---

## 3. Incrustar en OJS

En un **Custom Block** (o en la plantilla del tema) de OJS:

```html
<script src="https://radar.revistas.up.edu.mx/app/embed.js"
        data-mode="conversation"
        data-lang="es"
        data-limit="5"
        data-theme="rpc"></script>
```

Modos: `conversation` (cita RPC + corpus + CFP), `cfp` (call vigente), `latest` (recientes).

### Si OJS usa CSP
Permite el origen del radar en `frame-src` (y `script-src` si aplica):

```
Content-Security-Policy: frame-src 'self' https://radar.revistas.up.edu.mx;
```

El iframe es `https`, así que debe servirse por HTTPS para evitar contenido mixto.

---

## 4. LLM en la nube (diálogo socrático 24/7, sin tu PC)

Para que el método socrático con IA funcione con tu computadora apagada, apunta el
radar a un endpoint OpenAI-compatible. Con **Groq** (capa gratuita amplia):

1. Crea una API key en https://console.groq.com/keys (empieza con `gsk_`).
2. Define estas variables (en el panel de Render o en un `.env` del VPS):

```env
RADAR_LLM_URL=https://api.groq.com/openai/v1
RADAR_LLM_MODEL=llama-3.3-70b-versatile
RADAR_LLM_API_KEY=gsk_tu_clave
```

3. Reinicia/redeploy. El diálogo socrático ya no depende de tu LM Studio.

Notas:
- Groq respeta `response_format` (JSON), así que el radar obtiene preguntas y FINER válidos.
- Modelos sugeridos: `llama-3.3-70b-versatile` (calidad) o `llama-3.1-8b-instant` (velocidad).
- Si no defines `RADAR_LLM_API_KEY`, el radar cae al fallback de plantillas y lo avisa en la UI.
- Para volver a tu LM Studio local: `RADAR_LLM_URL=http://127.0.0.1:1234/v1` (o la IP de tu equipo).

Alternativas compatibles (mismo formato, cambia URL/modelo/key): Together, OpenRouter,
DeepSeek, o un Ollama con GPU (`http://IP:11434/v1`).

---

## 5. Qué NO va en la nube (y por qué)

- **LM Studio local**: solo si quieres seguir usando tu equipo. En la nube se sustituye
  por el LLM remoto de la sección 4.
- **Cosecha desde datacenter**: SciELO puede bloquear IPs de nube (anti-bot). Si pasa,
  cosecha desde tu equipo y sube `radar.db`, o usa el dump/API oficial de cada fuente.

---

## 6. Actualizar el catálogo manualmente

```bash
# VPS
docker compose run --rm harvester sh -c "python -m radar.harvester.cli --days 90 --max-articles 2000"

# Render: usa el Cron Job "Run now" del panel, o espera al ciclo.
```
