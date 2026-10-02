import json
import logging
import re
import sqlite3
import httpx
from . import config
from .normalize import norm
from .topics import COMMUNICATION_FIELDS

log = logging.getLogger("radar.socratic")

QUESTION_TEMPLATES = {
    "ecologia_medios": [
        "¿Tu indagación se enfoca en el impacto antropológico y cognitivo del medio tecnológico, o en la economía política de las plataformas?",
        "¿Consideras la tecnología como una herramienta instrumental o como un entorno cultural que reconfigura las relaciones humanas?",
        "¿Pretendes abordar modelos algorítmicos concretos (IA, redes sociales) o la dimensión teórica/ética de la extensión humana?"
    ],
    "comunicacion_politica": [
        "¿Te interesa más el emisor (estrategias de campaña, encuadres discursivos) o el impacto cognitivo en la ciudadanía (polarización, desinformación)?",
        "¿Tu foco analítico se sitúa en elecciones y partidos institucionales, o en movilizaciones espontáneas y debates en redes?",
        "¿Planeas analizar el fenómeno desde la desinformación deliberada o desde la fragmentación de la esfera pública?"
    ],
    "periodismo_digital": [
        "¿Observas las rutinas y condiciones laborales de los periodistas o las nuevas fórmulas narrativas (pódcast, TikTok, newsletters)?",
        "¿Tu objeto de estudio abarca medios consolidados tradicionales o iniciativas nativas digitales y de proximidad?",
        "¿Te interesa la verificación (fact-checking) y la credibilidad, o la automatización y la inteligencia artificial en redacciones?"
    ],
    "comunicacion_social_comunitaria": [
        "¿Tu investigación parte de la comunicación como herramienta de resistencia y derechos humanos, o como proceso de apropiación identitaria?",
        "¿Pones el acento en comunidades rurales, originarias o colectivos urbanos y de género?",
        "¿El abordaje metodológico es participativo/etnográfico o de análisis discursivo de contenidos alternativos?"
    ],
    "comunicacion_cientifica_salud": [
        "¿Tratas la divulgación científica masiva hacia el público general o la comunicación institucional y de riesgos en crisis sanitarias?",
        "¿El reto principal que exploras es la alfabetización científica o el combate a la pseudociencia y la infodemia?",
        "¿Te sitúas en el ámbito biomédico/salud, o en la crisis climática y ambiental?"
    ],
    "audiovisual_ficcion_transmedia": [
        "¿Tu interés reside en las estructuras narrativas y el guion, o en los hábitos de consumo y comunidades de fans en plataformas de streaming?",
        "¿Analizas la ficción cinematográfica/televisiva o formatos interactivos emergentes como los videojuegos y el metaverso?",
        "¿Buscas explorar la dimensión estética/autoral o la lógica de las industrias culturales globales?"
    ],
    "comunicacion_organizacional": [
        "¿Te centras en la gestión de crisis y reputación corporativa externa o en la comunicación interna y clima organizacional?",
        "¿Abordas organizaciones con fines de lucro o instituciones públicas y del tercer sector?",
        "¿El énfasis está en la sostenibilidad y responsabilidad social (RSC) o en el branding y posicionamiento de marca?"
    ],
    "educomunicacion_alfabetizacion": [
        "¿Tu perspectiva apunta a la enseñanza formal en escuelas/universidades o al aprendizaje informal y consumos juveniles en redes?",
        "¿Buscas medir competencias críticas frente a las pantallas o la capacitación técnica en producción de contenidos?",
        "¿Te interesa la protección de audiencias vulnerables (infancia/juventud) o el empoderamiento prosumidor?"
    ],
}

# Criterios FINER: cada pregunta del diálogo apunta a uno de ellos.
FINER_CRITERIA = [
    {"id": "factible", "label": "Factible", "hint": "¿Se puede realizar con los recursos, el tiempo y el acceso a datos o muestra disponibles?"},
    {"id": "interesante", "label": "Interesante", "hint": "¿Resulta atractivo para quien investiga y para la comunidad académica?"},
    {"id": "novedosa", "label": "Novedosa", "hint": "¿Aporta conocimiento nuevo o replica lo que ya existe en el corpus?"},
    {"id": "etica", "label": "Ética", "hint": "¿Evita dañar a participantes y resguarda consentimiento y datos sensibles?"},
    {"id": "relevante", "label": "Relevante", "hint": "¿Tiene impacto real en la agenda, la política pública o la práctica?"},
]
FINER_IDS = [c["id"] for c in FINER_CRITERIA]
_FINER_LABEL = {c["id"]: c["label"] for c in FINER_CRITERIA}
_FINER_HINT = {c["id"]: c["hint"] for c in FINER_CRITERIA}

DEFAULT_MAX_TURNS = 4

# Escalera socrática (adaptada del método Sócrates): de lo simple a lo complejo.
QUESTION_LADDER = [
    {"id": "clarifying", "label": "Aclarar", "purpose": "Saca a la luz supuestos: «Dijiste X, ¿qué razonamiento te llevó ahí?»"},
    {"id": "probing", "label": "Profundizar", "purpose": "Excava el detalle: «¿Qué pasaría si Y no existiera?»"},
    {"id": "connecting", "label": "Conectar", "purpose": "Enlaza conceptos: «¿Cómo se relaciona esto con Z?»"},
    {"id": "counter", "label": "Contraponer", "purpose": "Desafía: «¿Y si fuera B en lugar de A?»"},
    {"id": "hypothetical", "label": "Hipotetizar", "purpose": "Explora implicaciones: «Si esto se llevara a cabo, ¿qué problemas surgirían?»"},
]
QUESTION_KINDS = [q["id"] for q in QUESTION_LADDER]
_KIND_LABEL = {q["id"]: q["label"] for q in QUESTION_LADDER}

# Esquemas JSON (decodificación restringida en LM Studio) para evitar JSON inválido.
_FINER_SCHEMA = {
    "type": "object",
    "properties": {
        cid: {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["ok", "parcial", "pendiente"]},
                "note": {"type": "string"},
            },
            "required": ["status", "note"],
            "additionalProperties": False,
        }
        for cid in FINER_IDS
    },
    "required": FINER_IDS,
    "additionalProperties": False,
}
ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "field_id": {"type": "string"},
        "epistemic_reflection": {"type": "string"},
        "socratic_questions": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": QUESTION_KINDS},
                    "criterion": {"type": "string", "enum": FINER_IDS},
                    "question": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["kind", "criterion", "question", "rationale"],
                "additionalProperties": False,
            },
        },
        "finer": _FINER_SCHEMA,
        "done": {"type": "boolean"},
    },
    "required": ["field_id", "epistemic_reflection", "socratic_questions", "finer", "done"],
    "additionalProperties": False,
}
CONCERT_SCHEMA = {
    "type": "object",
    "properties": {
        "recommended_keywords": {"type": "array", "items": {"type": "string"}},
        "horizon_summary": {"type": "string"},
    },
    "required": ["recommended_keywords", "horizon_summary"],
    "additionalProperties": False,
}


def _clean_reasoning(text: str) -> str:
    """Elimina etiquetas <think>...</think> de modelos de razonamiento (como Phi-4)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


_LLM_ERROR: str | None = None


def _llm_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if config.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {config.LLM_API_KEY}"
    return headers


def _call_lmstudio(messages: list[dict], timeout: float = None, schema: dict | None = None) -> str | None:
    """Envía mensajes a un endpoint OpenAI-compatible (LM Studio local o remoto, p. ej. Groq).

    Si se pasa `schema`, intenta salida con json_schema; si el proveedor no lo soporta,
    reintenta con json_object y, por último, sin response_format.
    Devuelve el contenido o None. El motivo del fallo queda en `_LLM_ERROR`.
    """
    global _LLM_ERROR
    _LLM_ERROR = None
    url = f"{config.LLM_URL.rstrip('/')}/chat/completions"
    t = timeout or config.LMSTUDIO_TIMEOUT
    to = httpx.Timeout(t, connect=8.0)
    base_payload: dict = {
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 6000,
    }
    if config.LLM_MODEL:
        base_payload["model"] = config.LLM_MODEL
    if schema:
        schema_fmt = {
            "type": "json_schema",
            "json_schema": {"name": "radar_json", "strict": True, "schema": schema},
        }
    else:
        schema_fmt = {"type": "json_object"}
    object_fmt = {"type": "json_object"}
    attempts = [
        {**base_payload, "response_format": schema_fmt},
        {**base_payload, "response_format": object_fmt},
        dict(base_payload),
    ]
    last_status = None
    last_detail = None
    try:
        with httpx.Client(timeout=to) as client:
            for payload in attempts:
                resp = client.post(url, json=payload, headers=_llm_headers())
                last_status = resp.status_code
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices") or []
                    if not choices:
                        _LLM_ERROR = "El modelo no devolvió ninguna respuesta ('choices' vacío)."
                        return None
                    msg = choices[0].get("message") or {}
                    content = (msg.get("content") or "").strip()
                    if not content:
                        content = (msg.get("reasoning_content") or msg.get("reasoning") or "").strip()
                    if not content:
                        _LLM_ERROR = "El modelo no devolvió contenido de texto."
                        return None
                    if choices[0].get("finish_reason") == "length":
                        log.warning("El LLM truncó la respuesta (finish_reason=length)")
                    return _clean_reasoning(content)
                # Guarda el detalle del error por si el siguiente intento también falla
                try:
                    last_detail = (resp.json().get("error") or {}).get("message")
                except Exception:
                    last_detail = None
                # 400/422 suelen indicar response_format no soportado: probamos el siguiente
                if resp.status_code not in (400, 404, 422):
                    break
            _LLM_ERROR = last_detail or f"HTTP {last_status}"
            log.warning("LLM respondió %s: %s", last_status, _LLM_ERROR)
            return None
    except Exception as e:
        _LLM_ERROR = f"No se pudo contactar el LLM ({config.LLM_URL}): {e}"
        log.debug("LLM no disponible o no responde (%s). Usando fallback ontológico.", e)
        return None


def _loads_lenient(text: str) -> dict | None:
    """json.loads tolerante: acepta comas finales y objetos envueltos en texto."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    # Elimina comas finales antes de } o ] (error frecuente en modelos pequeños)
    cleaned = re.sub(r",(\s*[}\]])", r"\1", text)
    try:
        return json.loads(cleaned)
    except Exception:
        return None


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    clean = _clean_reasoning(text)
    # Prueba cada bloque ```json ... ``` que aparezca
    for m in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", clean, re.DOTALL):
        parsed = _loads_lenient(m.group(1))
        if parsed is not None:
            return parsed
    # Si no, toma desde la primera { hasta la última }
    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1 and end > start:
        return _loads_lenient(clean[start : end + 1])
    return None


def _score_fields(text_norm: str) -> list[tuple[int, dict, list[str]]]:
    """Puntúa los campos canónicos según solapamiento de keywords con el texto."""
    tokens = set(text_norm.split())
    ranked = []
    for f in COMMUNICATION_FIELDS:
        score = 0
        matches = []
        for kw in f["keywords_es"] + f["keywords_pt"]:
            nkw = norm(kw)
            if " " in nkw and nkw in text_norm:
                score += 4
                matches.append(kw)
            elif nkw in tokens:
                score += 2
                matches.append(kw)
        ranked.append((score, f, matches))
    ranked.sort(key=lambda x: -x[0])
    return ranked


def _related_papers(raw_text: str, conn: sqlite3.Connection, top_k: int = 4) -> tuple[list[str], list[dict]]:
    """Recupera contexto bibliográfico real con BGE-M3 y devuelve títulos y resultados crudos."""
    bge_results = []
    try:
        from . import vector_store
        bge_results = vector_store.search(raw_text, top_k=top_k)
    except Exception as e:
        log.debug("Error consultando vector_store: %s", e)
        return [], []

    related = []
    if bge_results:
        placeholders = ",".join("?" for _ in bge_results)
        dois = [r["doi"] for r in bge_results]
        try:
            rows = conn.execute(
                f"SELECT doi, title, journal_title FROM articles WHERE doi IN ({placeholders})",
                dois
            ).fetchall()
            row_map = {r["doi"]: r for r in rows}
            for r in bge_results:
                if r["doi"] in row_map:
                    item = row_map[r["doi"]]
                    related.append(f"«{item['title']}» ({item['journal_title']})")
        except Exception:
            pass
    return related, bge_results


def _history_block(history: list[dict]) -> str:
    """Formatea los turnos previos del diálogo para el prompt."""
    if not history:
        return "Aún no hay turnos previos: este es el primer turno del diálogo socrático."
    lines = ["Diálogo sostenido hasta ahora:"]
    for i, h in enumerate(history, 1):
        lines.append(f"Turno {i}:")
        for q in h.get("questions") or []:
            if isinstance(q, dict):
                tag = q.get("criterion_label") or _FINER_LABEL.get(q.get("criterion"), "FINER")
                lines.append(f"  Pregunta ({tag}): {q.get('question')}")
            else:
                lines.append(f"  Pregunta: {q}")
        ans = (h.get("answer") or "").strip()
        lines.append(f"  Respuesta del investigador: {ans or '(sin respuesta)'}")
    return "\n".join(lines)


def _normalize_questions(raw_qs, history: list[dict]) -> list[dict]:
    """Normaliza las preguntas del LLM a dicts {kind, criterion, question, rationale}, sin repetir."""
    used = set()
    for h in history:
        for q in h.get("questions") or []:
            if isinstance(q, dict) and q.get("question"):
                used.add(str(q["question"]).strip().lower())
            elif isinstance(q, str) and q.strip():
                used.add(q.strip().lower())

    out: list[dict] = []
    for i, item in enumerate(raw_qs or []):
        if isinstance(item, dict):
            qtext = str(item.get("question") or "").strip()
            cid = str(item.get("criterion") or "").strip().lower()
            kind = str(item.get("kind") or "").strip().lower()
            rationale = str(item.get("rationale") or "").strip()
        else:
            qtext = str(item or "").strip()
            cid = ""
            kind = ""
            rationale = ""
        if not qtext or qtext.lower() in used:
            continue
        if cid not in FINER_IDS:
            cid = FINER_IDS[i % len(FINER_IDS)]
        if kind not in QUESTION_KINDS:
            kind = QUESTION_KINDS[i % len(QUESTION_KINDS)]
        out.append({
            "kind": kind,
            "kind_label": _KIND_LABEL[kind],
            "criterion": cid,
            "criterion_label": _FINER_LABEL[cid],
            "question": qtext,
            "rationale": rationale or f"Pregunta de tipo «{_KIND_LABEL[kind]}» para resolver el criterio FINER «{_FINER_LABEL[cid]}».",
        })
        if len(out) >= 3:
            break
    return out


def _normalize_finer(raw) -> dict:
    """Garantiza los 5 criterios FINER con estado válido ('ok'|'parcial'|'pendiente')."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for c in FINER_CRITERIA:
        item = raw.get(c["id"]) if isinstance(raw.get(c["id"]), dict) else {}
        status = str(item.get("status") or "pendiente").strip().lower()
        if status not in ("ok", "parcial", "pendiente"):
            status = "parcial"
        out[c["id"]] = {"status": status, "note": str(item.get("note") or "").strip()}
    return out


def _fallback_finer(history: list[dict]) -> dict:
    """FINER heurístico sin LLM: marca 'parcial' los criterios ya abordados y con respuesta."""
    out = {c["id"]: {"status": "pendiente", "note": ""} for c in FINER_CRITERIA}
    for h in history:
        if not (h.get("answer") or "").strip():
            continue
        for q in h.get("questions") or []:
            cid = q.get("criterion") if isinstance(q, dict) else None
            if cid in out and out[cid]["status"] == "pendiente":
                out[cid]["status"] = "parcial"
    return out


def _fallback_questions(field: dict, history: list[dict]) -> list[dict]:
    """Preguntas de reserva (plantillas por campo) rotando criterios FINER y tipos de la escalera."""
    templates = QUESTION_TEMPLATES.get(field["id"], QUESTION_TEMPLATES["ecologia_medios"])
    start = (len(history) * 3) % len(FINER_CRITERIA)
    kind_start = (len(history) * 3) % len(QUESTION_LADDER)
    questions = []
    for i in range(min(3, len(FINER_CRITERIA))):
        crit = FINER_CRITERIA[(start + i) % len(FINER_CRITERIA)]
        kind = QUESTION_LADDER[(kind_start + i) % len(QUESTION_LADDER)]
        questions.append({
            "kind": kind["id"],
            "kind_label": kind["label"],
            "criterion": crit["id"],
            "criterion_label": crit["label"],
            "question": templates[i % len(templates)],
            "rationale": f"Pregunta de tipo «{kind['label']}» para evaluar el criterio FINER «{crit['label']}»: {crit['hint']}",
        })
    return questions


def analyze_inquiry(raw_text: str, conn: sqlite3.Connection,
                    history: list[dict] | None = None,
                    max_turns: int = DEFAULT_MAX_TURNS) -> dict:
    """Conduce un turno del diálogo socrático y evalúa el avance con FINER.

    `history` es la lista de turnos previos: [{"questions": [...], "answer": "..."}].
    En el primer turno se envía vacía. Si LM Studio está activo se usa el LLM (RAG);
    si no, se recurre a la heurística ontológica.
    """
    global _LLM_ERROR
    history = [h for h in (history or []) if isinstance(h, dict)]
    turn = len(history) + 1
    text_norm = norm(raw_text)

    related_papers, bge_results = _related_papers(raw_text, conn)

    ranked_fields = _score_fields(text_norm)
    best_field = ranked_fields[0][1] if ranked_fields and ranked_fields[0][0] > 0 else COMMUNICATION_FIELDS[0]
    sec_field = ranked_fields[1][1] if len(ranked_fields) > 1 and ranked_fields[1][0] > 0 else None
    field_id = best_field["id"]

    reflection = (
        f"Tu inquietud se inscribe principalmente en el campo de «{best_field['name']}». "
        "Para que el radar no sea una simple búsqueda de texto, concertemos qué vertiente de este campo "
        "dialoga verdaderamente con tu proyecto."
    )

    # ---- LLM (RAG socrático + FINER) ----
    fields_summary = "\n".join(f"- {f['id']}: {f['name']} ({f['description']})" for f in COMMUNICATION_FIELDS)
    papers_context = "\n".join(f"- {p}" for p in related_papers[:3]) if related_papers else "Catálogo general de 155 revistas."
    criteria_txt = "\n".join(f"- {c['id']} ({c['label']}): {c['hint']}" for c in FINER_CRITERIA)
    ladder_txt = "\n".join(f"- {q['id']} ({q['label']}): {q['purpose']}" for q in QUESTION_LADDER)

    prompt = f"""Eres un tutor socrático y dictaminador académico senior en Ciencias de la Comunicación para la Revista Panamericana de Comunicación.
Sostienes un diálogo socrático REAL para acotar el objeto de estudio de un investigador.

REGLA ABSOLUTA: NUNCA des la respuesta ni expliques el concepto. Solo haces preguntas que ayuden al investigador a descubrirla por sí mismo. Si en el historial el investigador pide la respuesta, rediriges con otra pregunta. No des pistas tan obvias que equivalgan a la respuesta.

Inquietud inicial del investigador:
"{raw_text}"

{_history_block(history)}

Artículos científicos reales afines encontrados en el catálogo iberoamericano:
{papers_context}

Campos canónicos de la disciplina:
{fields_summary}

Criterios FINER (evalúa cada uno con "ok", "parcial" o "pendiente" y una nota breve):
{criteria_txt}

Escalera de preguntas socráticas (sube de lo simple a lo complejo; usa un tipo distinto por pregunta):
{ladder_txt}

Tu tarea en ESTE turno ({turn} de {max_turns}):
1. Selecciona el campo canónico más adecuado (field_id).
2. Redacta una 'epistemic_reflection' (2-3 frases) que NO resuelva la pregunta: que reconozca lo ya dicho y devuelva el desafío al investigador.
3. Formula EXACTAMENTE 3 'socratic_questions' NUEVAS (no repitas las anteriores). Cada una debe indicar su tipo de la escalera ("kind": clarifying|probing|connecting|counter|hypothetical) y el criterio FINER que busca resolver ("criterion"). Adapta la profundidad a lo que el investigador ya respondió: si fue vago, aclara; si avanzó, contrapon o hipotetiza. Si "done" es true, puedes dar solo 1.
4. Evalúa los 5 criterios FINER según lo que el investigador ha precisado hasta ahora.
5. Si "done" es true, la 'epistemic_reflection' debe pedirle que resuma con sus palabras lo acordado. Indica "done": true solo si TIENES al menos una respuesta del investigador en el historial Y ya hay delimitación suficiente (objeto, método, criterio de novedad y encuadre ético). En el PRIMER turno (sin respuestas) "done" debe ser SIEMPRE false.

Devuelve ÚNICAMENTE un objeto JSON válido con esta estructura:
{{
  "field_id": "id_del_campo",
  "epistemic_reflection": "texto de la reflexión...",
  "socratic_questions": [
    {{"kind": "clarifying", "criterion": "factible", "question": "¿Pregunta 1...?", "rationale": "por qué ayuda a FINER..."}}
  ],
  "finer": {{
    "factible": {{"status": "parcial", "note": "..."}},
    "interesante": {{"status": "pendiente", "note": "..."}},
    "novedosa": {{"status": "pendiente", "note": "..."}},
    "etica": {{"status": "pendiente", "note": "..."}},
    "relevante": {{"status": "pendiente", "note": "..."}}
  }},
  "done": false
}}"""

    msgs = [
        {"role": "system", "content": "Eres un mentor socrático riguroso: nunca das la respuesta, solo preguntas. Responde siempre con un objeto JSON válido."},
        {"role": "user", "content": prompt},
    ]
    llm_resp = None
    parsed = None
    for _attempt in range(2):  # un reintento si el modelo devuelve JSON inválido
        llm_resp = _call_lmstudio(msgs, schema=ANALYZE_SCHEMA)
        if llm_resp:
            parsed = _extract_json(llm_resp)
            if parsed:
                break
    if llm_resp and parsed is None:
        _LLM_ERROR = "El modelo no devolvió un JSON válido tras dos intentos."

    questions: list[dict] = []
    finer: dict | None = None
    done = False
    used_llm = False

    if parsed:
        matched_field = next((f for f in COMMUNICATION_FIELDS if f["id"] == parsed.get("field_id")), None)
        if matched_field:
            best_field = matched_field
            field_id = matched_field["id"]
        if parsed.get("epistemic_reflection"):
            reflection = str(parsed["epistemic_reflection"]).strip()
        questions = _normalize_questions(parsed.get("socratic_questions"), history)
        finer = _normalize_finer(parsed.get("finer"))
        used_llm = True
        # El primer turno nunca debe cerrarse: exigimos al menos una respuesta.
        done = bool(parsed.get("done")) and turn >= 2

    # ---- Fallbacks heurísticos ----
    if not questions:
        questions = _fallback_questions(best_field, history)
    if finer is None:
        finer = _fallback_finer(history)
    # Si el diálogo sigue abierto, garantiza 3 preguntas (rellena con plantillas del campo).
    if not done and len(questions) < 3:
        have = {q["question"].strip().lower() for q in questions}
        for q in _fallback_questions(best_field, history):
            if q["question"].strip().lower() not in have:
                questions.append(q)
                have.add(q["question"].strip().lower())
            if len(questions) >= 3:
                break
    # Cierre natural: si ya hay al menos un turno respondido y todos los criterios
    # están cubiertos (ok/parcial), no hace falta seguir preguntando.
    if not done and turn >= 2 and all(v["status"] in ("ok", "parcial") for v in finer.values()):
        done = True
    if turn >= max_turns:
        done = True
    if done:
        questions = questions[:1]  # al cerrar basta un recordatorio, no tres preguntas

    # Muestra de densidad en el catálogo
    kw_cands = best_field["keywords_es"][:4] + best_field["keywords_pt"][:2]
    density_sample = 0
    try:
        for kw in kw_cands:
            if not kw:
                continue
            like = f"%{kw.strip()}%"
            n = conn.execute(
                "SELECT count(*) FROM articles WHERE title LIKE ? OR abstract LIKE ? OR keywords LIKE ?",
                (like, like, like),
            ).fetchone()[0]
            density_sample = max(density_sample, n)
    except Exception:
        density_sample = 0
    if not density_sample:
        density_sample = len(bge_results) if bge_results else 15

    return {
        "status": "dialogue",
        "turn": turn,
        "max_turns": max_turns,
        "done": done,
        "engine": "llm" if used_llm else "fallback",
        "engine_note": None if used_llm else (_LLM_ERROR or "LM Studio no disponible; se usaron plantillas del catálogo."),
        "inquiry": raw_text,
        "primary_field": {
            "id": best_field["id"],
            "name": best_field["name"],
            "description": best_field["description"],
            "journals_focus": best_field["journals_focus"],
        },
        "secondary_field": {
            "id": sec_field["id"],
            "name": sec_field["name"],
        } if sec_field else None,
        # Compatibilidad: clientes antiguos renderizan strings; los nuevos usan el detalle.
        "socratic_questions": [q["question"] for q in questions],
        "socratic_questions_detail": questions,
        "epistemic_reflection": reflection,
        "finer": finer,
        "finer_criteria": FINER_CRITERIA,
        "question_ladder": QUESTION_LADDER,
        "corpus_density_hint": f"Existen al menos {density_sample} publicaciones recientes en el catálogo vinculadas a este eje.",
    }


def concert_radar(field_id: str, inquiry: str, reflection: str, conn: sqlite3.Connection,
                  finer: dict | None = None) -> dict:
    """Concierta el radar temático utilizando LLM si está disponible o heurística ontológica."""
    field = next((f for f in COMMUNICATION_FIELDS if f["id"] == field_id), COMMUNICATION_FIELDS[0])

    finer_txt = ""
    if finer:
        lines = []
        for c in FINER_CRITERIA:
            item = finer.get(c["id"]) or {}
            status = item.get("status", "pendiente")
            note = item.get("note", "")
            lines.append(f"- {c['label']}: {status}" + (f" ({note})" if note else ""))
        finer_txt = "\nEvaluación FINER del diálogo:\n" + "\n".join(lines)

    prompt = f"""Eres un coordinador editorial y bibliómetra de la Revista Panamericana de Comunicación.
El investigador inició con la indagación: "{inquiry}"
Y tras el diálogo socrático, reflexionó y delimitó: "{reflection}"
Campo disciplinar acordado: {field['name']}.
{finer_txt}

Tu tarea es concertar el horizonte de vigilancia bibliográfica:
1. Generar de 6 a 8 palabras clave / descriptores de élite (mezcla balanceada en español y portugués) que sirvan para indexar y rastrear papers en SciELO, Redalyc y Crossref.
2. Redactar un 'horizon_summary' elegante (2 frases) que sintetice el acuerdo epistemológico.

Devuelve ÚNICAMENTE un JSON válido con esta estructura:
{{
  "recommended_keywords": ["descriptor 1", "descriptor 2", "descriptor 3", "descriptor 4", "descriptor 5", "descriptor 6"],
  "horizon_summary": "texto del horizonte..."
}}"""

    cmsgs = [
        {"role": "system", "content": "Responde siempre en formato JSON válido. Eres un bibliómetra de élite en comunicación iberoamericana."},
        {"role": "user", "content": prompt},
    ]
    parsed = None
    for _attempt in range(2):
        llm_resp = _call_lmstudio(cmsgs, schema=CONCERT_SCHEMA)
        if llm_resp:
            parsed = _extract_json(llm_resp)
            if parsed and parsed.get("recommended_keywords"):
                break

    final_keywords_list = []
    horizon_summary = ""

    if parsed and parsed.get("recommended_keywords"):
        final_keywords_list = [str(k).strip() for k in parsed["recommended_keywords"] if str(k).strip()]
        horizon_summary = parsed.get("horizon_summary", "")

    # Fallback si LLM no estaba activo o no devolvió keywords
    if not final_keywords_list:
        combined = norm(f"{inquiry} {reflection}")
        toks = [t for t in combined.split() if len(t) > 4]
        descriptors_es = list(dict.fromkeys(field["keywords_es"][:5]))
        descriptors_pt = list(dict.fromkeys(field["keywords_pt"][:4]))
        user_specific = []
        for t in toks[:4]:
            if not any(t in norm(d) for d in descriptors_es + descriptors_pt):
                user_specific.append(t)
        final_keywords_list = (descriptors_es + descriptors_pt + user_specific)[:8]

    if not horizon_summary:
        horizon_summary = (
            f"Has concertado un horizonte de vigilancia en «{field['name']}». "
            f"El radar rastreará de forma continua publicaciones en español y portugués, "
            f"con prioridad en revistas de referencia como {', '.join(field['journals_focus'][:3])}."
        )

    final_keywords_str = ", ".join(final_keywords_list[:8])
    label = f"Radar Temático: {field['name'].split(',')[0].split(' y ')[0]}"

    return {
        "status": "concerted",
        "label": label,
        "field_id": field["id"],
        "field_name": field["name"],
        "field_name_pt": field["name_pt"],
        "recommended_keywords": final_keywords_str,
        "keywords_list": final_keywords_list[:8],
        "recommended_journals": field["journals_focus"],
        "horizon_summary": horizon_summary,
        "finer": finer or {},
    }
