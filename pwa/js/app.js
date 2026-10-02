/* Radar RPC — lógica del widget PWA */
"use strict";

const API = "/api";
const CONFIG_KEY = "radar-rpc-config";

const DEFAULT_CONFIG = {
  keywords: "comunicación política, ecología de los medios, narrativas televisivas, ética y estética",
  langs: ["es", "pt"],
  sources: ["scielo", "crossref", "openalex", "redalyc"],
  limit: 5,
  days: 1825,
  sort: "relevance",
};

const state = { config: loadConfig(), deferredPrompt: null };

/* ---------------- config ---------------- */
function loadConfig() {
  try {
    const raw = localStorage.getItem(CONFIG_KEY);
    if (raw) return { ...DEFAULT_CONFIG, ...JSON.parse(raw) };
  } catch (e) { /* ignorar */ }
  return { ...DEFAULT_CONFIG };
}
function saveConfig() {
  localStorage.setItem(CONFIG_KEY, JSON.stringify(state.config));
}

function readForm() {
  state.config.keywords = document.getElementById("keywords").value.trim();
  state.config.langs = [...document.querySelectorAll("#langs input:checked")].map(i => i.value);
  state.config.sources = [...document.querySelectorAll("#sources input:checked")].map(i => i.value);
  state.config.limit = parseInt(document.getElementById("limit").value, 10);
  state.config.days = parseInt(document.getElementById("days").value, 10);
  state.config.sort = document.getElementById("sort").value;
  saveConfig();
}
function writeForm() {
  document.getElementById("keywords").value = state.config.keywords;
  document.querySelectorAll("#langs input").forEach(i => { i.checked = state.config.langs.includes(i.value); });
  document.querySelectorAll("#sources input").forEach(i => { i.checked = state.config.sources.includes(i.value); });
  document.getElementById("limit").value = String(state.config.limit);
  document.getElementById("days").value = String(state.config.days);
  document.getElementById("sort").value = state.config.sort;
}

/* ---------------- api ---------------- */
async function api(path, params = {}, opts = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") qs.set(k, v); });
  const url = `${API}${path}${qs.toString() ? "?" + qs : ""}`;
  let resp;
  try {
    resp = await fetch(url, {
      method: opts.method || "GET",
      headers: opts.body ? { "Content-Type": "application/json", Accept: "application/json" } : { Accept: "application/json" },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch (e) {
    const alt = url.replace(window.location.origin, "");
    throw new Error(`no se pudo contactar ${alt} (${url}). ¿Está corriendo el backend? Usa "inicio.bat" o arranca uvicorn.`);
  }
  if (!resp.ok) throw new Error(`API ${resp.status}: ${url}`);
  return resp.json();
}

/* ---------------- render ---------------- */
const SOURCE_NAMES = { scielo: "SciELO", crossref: "Crossref", openalex: "OpenAlex", redalyc: "Redalyc" };
const FIELD_NAMES = { title: "título", keywords: "palabras clave del artículo", abstract: "resumen" };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function authorsLine(a) {
  const aus = (a.authors || []).map(au => `${au.family || ""} ${au.given || ""}`.trim()).filter(Boolean);
  if (!aus.length) return "Autores no disponibles";
  if (aus.length <= 3) return aus.join(", ");
  return `${aus.slice(0, 3).join(", ")} et al.`;
}

function articleCard(a) {
  const dateStr = (a.pub_date || "").slice(0, 10);
  const badges = [];
  badges.push(`<span class="badge src-${a.source}">◉ ${SOURCE_NAMES[a.source] || a.source}</span>`);
  if (a.access === "oa") badges.push(`<span class="badge oa">acceso abierto</span>`);
  if (a.cited_by > 0) badges.push(`<span class="badge cited">◆ ${a.cited_by} citas</span>`);
  if (a.lang) badges.push(`<span class="badge lang">${esc(a.lang)}</span>`);

  const kws = (a.keywords || []).filter(k => typeof k === "string").slice(0, 6)
    .map(k => `<span class="keyword-chip">${esc(k)}</span>`).join("");

  let why = "";
  const convWhy = (a.conversation && a.conversation.why) || [];
  if (convWhy.length) {
    why += `<div class="why"><b>⦿ ¿Por qué este artículo?</b> ${convWhy.map(esc).join(" · ")}</div>`;
  } else if (a.matched && a.matched.length) {
    const chips = a.matched.map(m =>
      `<span class="kw">«${esc(m.keyword)}»</span> en ${FIELD_NAMES[m.field] || m.field}`
    ).join(" · ");
    why = `<div class="why"><b>⦿ ¿Por qué este artículo?</b> Coincide con: ${chips}</div>`;
  }
  if (a.conversation && a.conversation.cites_rpc) {
    badges.push(`<span class="badge cited">cita RPC</span>`);
  }
  if (a.thematic_fields && a.thematic_fields.length) {
    badges.push(`<span class="badge thematic-field">🏷️ ${esc(a.thematic_fields[0].name)}</span>`);
  }

  const exportLinks = ["apa", "bibtex", "ris"].map(f =>
    `<a href="/api/articles/${encodeURIComponent(a.doi || "")}/citation?format=${f}" download>${f.toUpperCase()}</a>`
  ).join("");

  return `
  <article class="article">
    <span class="when">${dateStr || ""}</span>
    <h3><a href="${esc(a.url || `https://doi.org/${a.doi}`)}" target="_blank" rel="noopener">${esc(a.title)}</a></h3>
    <div class="meta">${esc(authorsLine(a))} — <span class="journal">${esc(a.journal_title || "Revista")}</span>${a.volume ? ` <b>${esc(a.volume)}</b>` : ""}${a.issue ? `(${esc(a.issue)})` : ""}${a.year ? ` · ${a.year}` : ""}</div>
    <div class="badges">${badges.join("")}</div>
    ${why}
    ${kws ? `<div class="keywords-line">${kws}</div>` : ""}
    <div class="export"><span class="sep">Citar:</span>${exportLinks}</div>
  </article>`;
}

async function renderFeed(retry = true) {
  const feed = document.getElementById("feed");
  // Skeletons mientras carga (UX-4)
  feed.innerHTML = '<div class="skeleton"></div>'.repeat(Math.min(state.config.limit || 5, 5));
  try {
    const data = await api("/feed", {
      keywords: state.config.keywords,
      langs: state.config.langs.join(","),
      sources: state.config.sources.join(","),
      limit: state.config.limit,
      days: state.config.days,
      sort: state.config.sort,
    });
    document.getElementById("stat-feed").textContent = String(data.count);
    if (!data.articles.length) {
      // Ayuda cuando no hay señales: cuántas coincidencias hay en una ventana mayor
      let hintHtml = "";
      let rows = [];
      if (data.hints && data.hints.wider_window) {
        rows = data.hints.wider_window.keyword_counts.filter(k => k.count > 0);
        if (rows.length) {
          hintHtml = `<p class="sub" style="margin-top:8px">Con ventana de 1 año:
            ${rows.map(k => `«${esc(k.keyword)}» → <b>${k.count}</b>`).join(" · ")}</p>
            <button class="btn sm cool" id="btn-widen" style="margin-top:10px">Ampliar ventana a 1 año</button>`;
        } else {
          hintHtml = `<p class="sub" style="margin-top:8px">Sin coincidencias ni en el último año en el catálogo actual.</p>`;
        }
      }
      feed.innerHTML = `<div class="empty"><p>🛰️ Sin señales con estos filtros.</p>
        <p class="sub">Prueba con otras palabras clave, revisa los separadores (coma, punto y coma o guion) o amplía la ventana temporal.</p>
        ${hintHtml}</div>`;
      if (rows.length) {
        document.getElementById("btn-widen").addEventListener("click", () => {
          state.config.days = 365;
          document.getElementById("days").value = "365";
          saveConfig();
          renderFeed();
        });
      }
      return;
    }
    feed.innerHTML = data.articles.map(articleCard).join("");
  } catch (e) {
    if (retry) { setTimeout(() => renderFeed(false), 1500); return; }
    feed.innerHTML = `<div class="empty"><p>⚠️ No se pudo contactar el radar: ${esc(e.message)}</p><p class="sub">Verifica que el backend esté corriendo (uvicorn) y recarga. Si abriste la app hace rato, prueba <a href="./" style="color:var(--cyan)">recargar la página</a>.</p></div>`;
  }
}

async function renderStats() {
  try {
    const st = await api("/stats");
    document.getElementById("stat-articles").textContent = st.articles;
    document.getElementById("stat-journals").textContent = st.journals;
  } catch (e) { /* no crítico */ }
}

async function renderSources() {
  try {
    const { sources } = await api("/sources");
    const box = document.getElementById("sources-status");
    box.innerHTML = Object.entries(sources).map(([name, s]) => {
      const ok = s.status === "ok";
      const cls = ok ? "ok" : (s.status === "error" ? "err" : "never");
      const stateTxt = ok ? "✔ operativa" : (s.status === "error" ? "✖ no disponible" : "sin cosecha aún");
      const detail = s.finished_at ? `${s.articles_found || 0} artículos · ${(s.finished_at || "").replace("T", " ").slice(0, 16)} UTC` : (s.notes || "");
      return `<div class="src-item ${cls}"><div class="name">${SOURCE_NAMES[name] || name}</div><div class="state">${stateTxt}</div><div class="detail">${esc(detail)}</div></div>`;
    }).join("");
  } catch (e) {
    document.getElementById("sources-status").innerHTML = `<span>No disponible</span>`;
  }
}

async function refreshSuggest() {
  const input = document.getElementById("keywords");
  const dl = document.getElementById("kw-suggest");
  const q = (input.value || "").split(",").pop().trim();
  if (q.length < 2) return;
  try {
    const { keywords } = await api("/suggest", { q, limit: 10 });
    dl.innerHTML = keywords.map(k => `<option value="${esc(k)}">`).join("");
  } catch (e) { /* silencioso */ }
}

/* ---------------- radar anclado (watch) ---------------- */
async function loadWatch() {
  const box = document.getElementById("watch-list");
  try {
    const data = await api("/watch/total");
    if (!data.pins.length) {
      box.innerHTML = `<p class="sub">Sin anclas todavía. Escribe tus keywords arriba y pulsa «📌 Anclar»: el radar te avisará cuando lleguen publicaciones nuevas que coincidan.</p>`;
      return;
    }
    box.innerHTML = data.pins.map(p => `
      <div class="pin">
        <div class="pin-info">
          <div class="pin-label">${esc(p.label)}</div>
          <div class="pin-kw">${esc(p.keywords)}</div>
        </div>
        <span class="pin-new">◉ ${p.new} nueva${p.new === 1 ? "" : "s"}</span>
        <button class="btn sm" data-pin-see="${p.id}">Ver nuevas</button>
        <button class="btn sm danger" data-pin-del="${p.id}" title="Desanclar">✕</button>
      </div>`).join("");
    box.querySelectorAll("[data-pin-see]").forEach(b =>
      b.addEventListener("click", () => showWatchNew(parseInt(b.dataset.pinSee, 10))));
    box.querySelectorAll("[data-pin-del]").forEach(b =>
      b.addEventListener("click", () => delWatch(parseInt(b.dataset.pinDel, 10))));
    maybeNotify(data.total);
  } catch (e) {
    box.innerHTML = `<span class="sub">Anclas no disponibles (${esc(e.message)})</span>`;
  }
}

async function addWatch() {
  const keywords = document.getElementById("keywords").value.trim();
  if (!keywords) return;
  try {
    await api("/watch", {}, { method: "POST", body: { keywords } });
    await loadWatch();
  } catch (e) {
    alert(`No se pudo anclar: ${e.message}`);
  }
}

async function delWatch(id) {
  try {
    await api(`/watch/${id}`, {}, { method: "DELETE" });
    await loadWatch();
    renderFeed();
  } catch (e) { /* ignorar */ }
}

async function showWatchNew(id) {
  const feed = document.getElementById("feed");
  feed.innerHTML = '<div class="skeleton"></div>'.repeat(3);
  try {
    const data = await api(`/watch/${id}/new`, { mark: 1, limit: 20 });
    const back = `<div class="why" style="margin-bottom:14px"><b>⦿ Nuevas publicaciones para «${esc(data.label)}»</b>
      <button class="btn sm cool" id="btn-back-radar" style="margin-left:10px">← Volver al radar</button></div>`;
    if (!data.articles.length) {
      feed.innerHTML = back + `<div class="empty"><p>✅ Al día. No hay publicaciones nuevas para este ancla.</p></div>`;
    } else {
      feed.innerHTML = back + data.articles.map(articleCard).join("");
    }
    document.getElementById("btn-back-radar").addEventListener("click", () => renderFeed());
    await loadWatch();
  } catch (e) {
    feed.innerHTML = `<div class="empty"><p>⚠️ ${esc(e.message)}</p></div>`;
  }
}

/* ---------------- notificaciones del navegador ---------------- */
const NOTIFY_COOLDOWN_KEY = "radar-obcc-notify-at";
async function maybeNotify(total) {
  try {
    if (!total || Notification.permission !== "granted" || !document.hidden) return;
    const last = parseInt(localStorage.getItem(NOTIFY_COOLDOWN_KEY) || "0", 10);
    if (Date.now() - last < 15 * 60 * 1000) return;
    localStorage.setItem(NOTIFY_COOLDOWN_KEY, String(Date.now()));
    const n = new Notification("Radar RPC", {
      body: `◉ ${total} nueva${total === 1 ? "" : "s"} publicación${total === 1 ? "" : "es"} coincide${total === 1 ? "" : "n"} con tus keywords ancladas`,
      icon: "icons/icon-192.png",
      tag: "radar-new",
    });
    n.onclick = () => { window.focus(); n.close(); };
  } catch (e) { /* sin permiso o no soportado */ }
}
function refreshNotifyButton() {
  const btn = document.getElementById("btn-notify");
  if ("Notification" in window && Notification.permission === "granted") {
    btn.textContent = "🔔 Notificaciones activadas";
    btn.classList.add("cool");
  } else {
    btn.textContent = "🔔 Activar notificaciones";
  }
}

/* ---------------- autores emergentes ---------------- */
async function renderEmerging() {
  const box = document.getElementById("authors-list");
  try {
    const data = await api("/authors", { sort: "emerging", days: 365, limit: 6 });
    if (!data.authors.length) {
      box.innerHTML = `<span class="sub">Aún no hay señales suficientes (se calcula tras cada cosecha).</span>`;
      return;
    }
    box.innerHTML = data.authors.map(a => `
      <div class="author-item">
        <div class="author-name">${esc(a.name)}</div>
        <div class="author-meta">${a.n} artículo${a.n === 1 ? "" : "s"} · primera publicación ${esc((a.first_pub_date || "").slice(0, 10))}</div>
        ${a.journals && a.journals.length ? `<div class="author-journals">📰 ${esc(a.journals.slice(0, 3).join(" · "))}</div>` : ""}
      </div>`).join("");
  } catch (e) {
    box.innerHTML = `<span class="sub">Autores no disponibles</span>`;
  }
}

/* ---------------- instalación PWA ---------------- */
window.addEventListener("beforeinstallprompt", e => {
  e.preventDefault();
  state.deferredPrompt = e;
  document.getElementById("install-wrap").hidden = false;
});
document.getElementById("btn-install").addEventListener("click", async () => {
  if (!state.deferredPrompt) return;
  state.deferredPrompt.prompt();
  await state.deferredPrompt.userChoice;
  state.deferredPrompt = null;
  document.getElementById("install-wrap").hidden = true;
});

/* ---------------- boot ---------------- */
document.getElementById("btn-apply").addEventListener("click", () => {
  readForm(); renderFeed(); refreshSuggest();
});
document.getElementById("btn-refresh").addEventListener("click", () => { renderFeed(); renderSources(); loadWatch(); renderEmerging(); });
document.getElementById("btn-pin").addEventListener("click", addWatch);
document.getElementById("btn-cfp").addEventListener("click", async () => {
  try {
    const data = await api("/cfp");
    const kws = (data.cfp && data.cfp.keywords) || [];
    document.getElementById("keywords").value = kws.slice(0, 6).join(", ");
    readForm();
    renderFeed();
  } catch (e) { /* silencioso */ }
});
document.getElementById("btn-notify").addEventListener("click", async () => {
  if (!("Notification" in window)) { alert("Tu navegador no soporta notificaciones"); return; }
  const p = await Notification.requestPermission();
  refreshNotifyButton();
  if (p === "granted") loadWatch();
});
document.getElementById("keywords").addEventListener("input", debounce(refreshSuggest, 400));
document.getElementById("keywords").addEventListener("keydown", e => {
  if (e.key === "Enter") {
    e.preventDefault();
    readForm();
    renderFeed();
    refreshSuggest();
  }
});

function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

/* ---------------- método socrático (diálogo multi-turno + FINER) ---------------- */
let currentSocraticData = null;
let currentConcertedData = null;
let socraticHistory = [];

function initSocratic() {
  const modal = document.getElementById("socratic-modal");
  const openBtn = document.getElementById("btn-open-socratic");
  const closeBtn = document.getElementById("btn-close-socratic");
  const analyzeBtn = document.getElementById("btn-socratic-analyze");
  const backBtn = document.getElementById("btn-socratic-back");
  const nextBtn = document.getElementById("btn-socratic-next");
  const concertBtn = document.getElementById("btn-socratic-concert");
  const pinBtn = document.getElementById("btn-socratic-pin");
  const applyBtn = document.getElementById("btn-socratic-apply");
  const reflectionInput = document.getElementById("socratic-reflection-input");

  if (!modal || !openBtn) return;

  const setBusy = (busy, label) => {
    [analyzeBtn, nextBtn, backBtn, concertBtn].forEach(b => { if (b) b.disabled = busy; });
    if (label) analyzeBtn.textContent = label;
  };

  const closeModal = () => {
    modal.hidden = true;
    modal.style.display = "none";
  };

  const openModal = () => {
    socraticHistory = [];
    currentSocraticData = null;
    currentConcertedData = null;
    document.getElementById("socratic-input").value = "";
    reflectionInput.value = "";
    document.getElementById("socratic-dialogue-log").innerHTML = "";
    document.getElementById("socratic-questions-list").innerHTML = "";
    document.getElementById("socratic-finer-panel").innerHTML = "";
    document.getElementById("socratic-turn-badge").textContent = "";
    modal.hidden = false;
    modal.style.display = "flex";
    document.getElementById("socratic-step-1").hidden = false;
    document.getElementById("socratic-step-2").hidden = true;
    document.getElementById("socratic-step-3").hidden = true;
    document.getElementById("socratic-input").focus();
  };

  const renderSocraticDialogue = () => {
    const d = currentSocraticData;
    if (!d) return;

    document.getElementById("socratic-turn-badge").textContent =
      `Turno ${d.turn || 1} de ${d.max_turns || 1}` + (d.done ? " · horizonte acotado" : "");

    // Aviso si el motor de IA no respondió (p. ej. LM Studio sin modelo cargado)
    const warn = document.getElementById("socratic-engine-warning");
    if (warn) {
      if (d.engine === "fallback") {
        warn.hidden = false;
        warn.textContent = `⚠️ Diálogo sin IA: ${d.engine_note || "LM Studio no disponible."} Carga un modelo en LM Studio (pestaña Developer) para el método socrático real con FINER.`;
      } else {
        warn.hidden = true;
        warn.textContent = "";
      }
    }
    document.getElementById("socratic-field-badge").textContent = `Campo: ${d.primary_field.name}`;
    document.getElementById("socratic-epistemic").textContent = d.epistemic_reflection || "";
    document.getElementById("socratic-density").textContent = d.corpus_density_hint || "";

    // Transcripción del diálogo previo
    const log = document.getElementById("socratic-dialogue-log");
    log.innerHTML = socraticHistory.map(h => {
      const qs = (h.questions || []).map(q => {
        const text = typeof q === "string" ? q : (q && q.question);
        return text ? `<div class="turn-q">💭 ${esc(text)}</div>` : "";
      }).join("");
      return `<div class="turn">${qs}<div class="turn-a">R: ${esc(h.answer || "")}</div></div>`;
    }).join("");

    // Panel FINER
    const labels = {};
    (d.finer_criteria || []).forEach(c => { labels[c.id] = c.label; });
    const finer = d.finer || {};
    document.getElementById("socratic-finer-panel").innerHTML = Object.keys(finer).map(id => {
      const it = finer[id] || {};
      const status = it.status || "pendiente";
      return `<div class="finer-item ${status}">
        <div class="finer-name"><span class="finer-dot"></span>${esc(labels[id] || id)}</div>
        ${it.note ? `<div class="finer-note">${esc(it.note)}</div>` : ""}
      </div>`;
    }).join("");

    // Preguntas del turno (cada una apunta a un criterio FINER)
    const qList = document.getElementById("socratic-questions-list");
    const qs = d.socratic_questions_detail || d.socratic_questions || [];
    qList.innerHTML = qs.map((q, i) => {
      const obj = typeof q === "string" ? { question: q } : (q || {});
      return `<div class="socratic-question-item" style="cursor:pointer" title="Haz clic para responder a esta pregunta" data-q-index="${i}">
        ${obj.kind_label ? `<span class="q-kind">${esc(obj.kind_label)}</span>` : ""}${obj.criterion_label ? `<span class="q-criterion">${esc(obj.criterion_label)}</span>` : ""}💭 ${esc(obj.question || "")}
        ${obj.rationale ? `<span class="q-rationale">${esc(obj.rationale)}</span>` : ""}
      </div>`;
    }).join("");
    qList.querySelectorAll("[data-q-index]").forEach(el => {
      el.addEventListener("click", () => {
        const q = qs[Number(el.dataset.qIndex)];
        const text = typeof q === "string" ? q : (q && q.question);
        if (!text) return;
        reflectionInput.value += (reflectionInput.value ? "\n\n" : "") + "R: " + text + "\n";
        reflectionInput.focus();
      });
    });

    nextBtn.hidden = !!d.done;
  };

  const composeReflection = () => {
    const parts = socraticHistory.map(h => (h.answer || "").trim()).filter(Boolean);
    const current = (reflectionInput.value || "").trim();
    if (current) parts.push(current);
    return parts.join("\n\n");
  };

  const runSocraticTurn = async (answer) => {
    const inquiry = (currentSocraticData && currentSocraticData.inquiry) ||
      document.getElementById("socratic-input").value.trim();
    if (!inquiry) return;
    if (answer != null) {
      const qs = currentSocraticData ? (currentSocraticData.socratic_questions_detail || currentSocraticData.socratic_questions) : [];
      socraticHistory.push({ questions: qs, answer });
    }
    setBusy(true, "Analizando…");
    try {
      currentSocraticData = await api("/socratic/analyze", {}, {
        method: "POST",
        body: { inquiry, history: socraticHistory },
      });
      renderSocraticDialogue();
      document.getElementById("socratic-step-1").hidden = true;
      document.getElementById("socratic-step-3").hidden = true;
      document.getElementById("socratic-step-2").hidden = false;
      if (answer != null) reflectionInput.value = "";
      reflectionInput.focus();
    } catch (e) {
      if (answer != null) socraticHistory.pop();
      alert(`Error en diálogo socrático: ${e.message}`);
    } finally {
      setBusy(false, "Comenzar Diálogo Socrático");
    }
  };

  openBtn.addEventListener("click", openModal);
  closeBtn.addEventListener("click", closeModal);

  // Cerrar haciendo clic fuera de la tarjeta o con Escape
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) closeModal();
  });

  analyzeBtn.addEventListener("click", () => runSocraticTurn(null));

  nextBtn.addEventListener("click", () => {
    const answer = reflectionInput.value.trim();
    if (!answer) {
      alert("Escribe tu respuesta antes de continuar el diálogo.");
      reflectionInput.focus();
      return;
    }
    runSocraticTurn(answer);
  });

  backBtn.addEventListener("click", () => {
    socraticHistory = [];
    currentSocraticData = null;
    document.getElementById("socratic-step-2").hidden = true;
    document.getElementById("socratic-step-1").hidden = false;
    document.getElementById("socratic-input").focus();
  });

  concertBtn.addEventListener("click", async () => {
    if (!currentSocraticData) return;
    concertBtn.disabled = true;
    concertBtn.textContent = "Concertando horizonte…";
    try {
      currentConcertedData = await api("/socratic/concert", {}, {
        method: "POST",
        body: {
          field_id: currentSocraticData.primary_field.id,
          inquiry: currentSocraticData.inquiry,
          reflection: composeReflection(),
          finer: currentSocraticData.finer || null,
        }
      });
      document.getElementById("socratic-result-title").textContent = currentConcertedData.label;
      document.getElementById("socratic-result-summary").textContent = currentConcertedData.horizon_summary;
      document.getElementById("socratic-result-kws").textContent = currentConcertedData.recommended_keywords;
      document.getElementById("socratic-result-journals").textContent = (currentConcertedData.recommended_journals || []).join(" · ");
      const fin = currentConcertedData.finer || {};
      const labels = {};
      (currentSocraticData.finer_criteria || []).forEach(c => { labels[c.id] = c.label; });
      document.getElementById("socratic-result-finer").textContent =
        Object.keys(fin).map(id => `${labels[id] || id}: ${fin[id].status}`).join(" · ") || "—";

      document.getElementById("socratic-step-2").hidden = true;
      document.getElementById("socratic-step-3").hidden = false;
    } catch (e) {
      alert(`Error al concertar: ${e.message}`);
    } finally {
      concertBtn.disabled = false;
      concertBtn.textContent = "Concertar mi Radar";
    }
  });

  pinBtn.addEventListener("click", async () => {
    if (!currentConcertedData) return;
    pinBtn.disabled = true;
    pinBtn.textContent = "Anclando…";
    try {
      await api("/watch", {}, {
        method: "POST",
        body: { keywords: currentConcertedData.recommended_keywords, label: currentConcertedData.label }
      });
      // Actualizar keywords en el formulario principal y cerrar modal
      document.getElementById("keywords").value = currentConcertedData.recommended_keywords;
      readForm();
      closeModal();
      await Promise.all([loadWatch(), renderFeed()]);
      const feedEl = document.getElementById("feed");
      if (feedEl) feedEl.scrollIntoView({ behavior: "smooth" });
    } catch (e) {
      alert(`Error al anclar: ${e.message}`);
    } finally {
      pinBtn.disabled = false;
      pinBtn.textContent = "📌 Anclar y Activar este Radar";
    }
  });

  applyBtn.addEventListener("click", async () => {
    if (!currentConcertedData) return;
    applyBtn.disabled = true;
    applyBtn.textContent = "Cargando publicaciones…";
    try {
      document.getElementById("keywords").value = currentConcertedData.recommended_keywords;
      closeModal();
      readForm();
      await renderFeed();
      const feedEl = document.getElementById("feed");
      if (feedEl) feedEl.scrollIntoView({ behavior: "smooth" });
    } catch (e) {
      alert(`Error al cargar feed: ${e.message}`);
    } finally {
      applyBtn.disabled = false;
      applyBtn.textContent = "Ver Publicaciones Ahora";
    }
  });
}

/* ---------------- match académico / conexión de pares (tinder) ---------------- */
async function loadRpcArticlesForMatch() {
  const select = document.getElementById("match-rpc-select");
  if (!select) return;
  try {
    const data = await api("/rpc/articles");
    select.innerHTML = '<option value="">-- Elige tu artículo en RPC o escribe tu tema al lado --</option>' +
      data.articles.map(a => `<option value="${a.id}">[${a.year || "RPC"}] ${esc(a.title.slice(0, 75))}… (${esc(a.authors_str.slice(0, 35))})</option>`).join("");
  } catch (e) { /* silencioso */ }
}

async function runAuthorMatch() {
  const select = document.getElementById("match-rpc-select");
  const input = document.getElementById("match-author-input");
  const grid = document.getElementById("match-cards-grid");
  const articleId = select ? select.value : "";
  const queryText = input ? input.value.trim() : "";

  if (!articleId && !queryText) {
    grid.innerHTML = `<div class="empty-match">Por favor selecciona un artículo de RPC o escribe el nombre del autor / línea de estudio.</div>`;
    return;
  }

  grid.innerHTML = '<div class="skeleton"></div>'.repeat(3);
  try {
    const params = { limit: 6 };
    if (articleId) params.article_id = articleId;
    if (queryText) params.topic = queryText;
    const data = await api("/authors/match", params);

    if (!data.matches || !data.matches.length) {
      grid.innerHTML = `<div class="empty-match">No se encontraron pares con suficiente afinidad en el catálogo actual para esta búsqueda.</div>`;
      return;
    }

    grid.innerHTML = data.matches.map(m => {
      const concepts = (m.shared_concepts || []).map(c => `<span class="concept-tag">#${esc(c)}</span>`).join("");
      const articles = (m.articles || []).map(a =>
        `<div class="match-article-item">
          📄 <a href="${a.doi ? 'https://doi.org/' + encodeURIComponent(a.doi) : '#'}" target="_blank" rel="noopener"><b>${esc(a.title || "")}</b></a>
          <span style="opacity:.7"> · ${esc(a.journal || "")}${a.year ? ' (' + a.year + ')' : ''}</span>
        </div>`
      ).join("");

      return `
      <div class="match-card">
        <div>
          <div class="match-card-top">
            <div>
              <div class="match-author-name">👤 ${esc(m.name)}</div>
              <div class="match-author-journal">📰 ${esc(m.journal)}</div>
            </div>
            <div class="match-meter">🔥 ${m.affinity}% Match</div>
          </div>
          <div class="match-rationale">⦿ ${esc(m.match_rationale)}</div>
          <div class="match-concepts">${concepts}</div>
          <div class="match-articles-list">${articles}</div>
        </div>
        <div class="match-card-actions">
          <button class="btn sm cool" data-follow-author="${esc(m.name)}">📌 Seguir a este autor</button>
        </div>
      </div>`;
    }).join("");

    grid.querySelectorAll("[data-follow-author]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const authorName = btn.dataset.followAuthor;
        try {
          await api("/watch", {}, { method: "POST", body: { keywords: authorName, label: `Autor par: ${authorName}` } });
          btn.textContent = "✔ Siguiendo";
          btn.disabled = true;
          loadWatch();
        } catch (e) {
          alert(`No se pudo seguir al autor: ${e.message}`);
        }
      });
    });

  } catch (e) {
    grid.innerHTML = `<div class="empty-match">Error buscando pares: ${esc(e.message)}</div>`;
  }
}

function initAuthorMatch() {
  const btn = document.getElementById("btn-find-matches");
  const select = document.getElementById("match-rpc-select");
  const input = document.getElementById("match-author-input");
  if (btn) btn.addEventListener("click", runAuthorMatch);
  if (select) select.addEventListener("change", () => {
    if (select.value) {
      if (input) input.value = "";
      runAuthorMatch();
    }
  });
  if (input) input.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (select) select.value = "";
      runAuthorMatch();
    }
  });
}

(async function init() {
  writeForm();
  refreshNotifyButton();
  initSocratic();
  initAuthorMatch();
  await Promise.all([
    renderFeed(),
    renderStats(),
    renderSources(),
    loadWatch(),
    renderEmerging(),
    loadRpcArticlesForMatch(),
  ]);
  if ("serviceWorker" in navigator) {
    let refreshing = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });
    try {
      const reg = await navigator.serviceWorker.register("sw.js");
      if (reg) reg.update();
    } catch (e) { /* SW opcional */ }
  }
})();