"""Harvester Redalyc vía OAI-PMH institucional (UAEMex / Redalyc).

Endpoints funcionales verificados:
  Primary:  http://redalycojs.uaemex.mx/redalyc/oai
  Fallback: http://148.215.1.70/redalyc/oai

Verbos soportados:
  - Identify
  - ListIdentifiers
  - ListRecords (con soporte de set=ISSN y resumptionToken)
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET

from .. import config
from ..normalize import unescape
from .base import Article, SourceUnavailable

log = logging.getLogger("radar.redalyc")

OAI_ENDPOINTS = [
    "http://redalycojs.uaemex.mx/redalyc/oai",
    "http://148.215.1.70/redalyc/oai",
]
OAI_BASE = OAI_ENDPOINTS[0]

API_BASE = "https://api.redalyc.org"
_OAINS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dXx]$")


def test_availability(http) -> tuple[bool, str, str]:
    """Ping al OAI de Redalyc; prueba endpoint primario y fallback.
    Devuelve (disponible, detalle, endpoint_activo).
    """
    last_err = "sin respuesta"
    for endpoint in OAI_ENDPOINTS:
        try:
            r = http.get(endpoint, params={"verb": "Identify"}, timeout=15)
            if r.status_code == 200 and ("Identify" in r.text or "repositoryName" in r.text):
                return True, "OAI-PMH operativo", endpoint
            last_err = f"HTTP {r.status_code}: {r.text[:60]}"
        except Exception as e:
            last_err = f"error de conexión ({type(e).__name__})"
            continue
    return False, last_err, OAI_ENDPOINTS[0]


def _dc_text(el: ET.Element, tag: str) -> list[str]:
    return [unescape(t.text or "").strip() for t in el.findall(f"dc:{tag}", _OAINS) if (t.text or "").strip()]


def parse_record(rec: ET.Element) -> Article | None:
    meta = rec.find(".//oai_dc:dc", _OAINS)
    if meta is None:
        return None
    titles = _dc_text(meta, "title")
    title = titles[0] if titles else None
    if not title or len(title) < 8:
        return None

    creators = _dc_text(meta, "creator")
    authors = []
    for c in creators:
        if "," in c:
            family, given = c.split(",", 1)
            authors.append({"given": given.strip(), "family": family.strip(), "orcid": None})
        else:
            authors.append({"given": c.strip(), "family": "", "orcid": None})

    date_vals = _dc_text(meta, "date") or []
    year = None
    pub_date = None
    if date_vals:
        m = re.match(r"(\d{4})", date_vals[0])
        if m:
            year = int(m.group(1))
            pub_date = date_vals[0][:10] if len(date_vals[0]) >= 10 else f"{m.group(1)}-01-01"

    doi = None
    ids = _dc_text(meta, "identifier")
    for i in ids:
        m = _DOI_RE.search(i)
        if m:
            doi = m.group(0).rstrip(".")
            break

    # ID de Redalyc a partir del header de OAI (oai:redalyc.org:12345)
    hdr_id = rec.find(".//oai:header/oai:identifier", _OAINS)
    if hdr_id is None:
        hdr_id = rec.find(".//oai:identifier", _OAINS)
    red_id = None
    if hdr_id is not None and hdr_id.text:
        m = re.search(r"oai:redalyc\.org:(\w+)", hdr_id.text)
        if m:
            red_id = m.group(1)

    url = f"https://doi.org/{doi}" if doi else (f"https://www.redalyc.org/articulo.oa?id={red_id}" if red_id else None)
    source_id = doi or (f"redalyc:{red_id}" if red_id else None)

    lang = None
    for i in ids:
        lm = re.search(r"/(es|pt|en)/", i)
        if lm:
            lang = lm.group(1)
            break
    if not lang:
        lang_dc = _dc_text(meta, "language")
        if lang_dc:
            lang = lang_dc[0][:2].lower()

    # ISSN desde setSpec en el header
    issn = None
    for s in rec.findall(".//oai:setSpec", _OAINS):
        if s.text and _ISSN_RE.match(s.text.strip()):
            issn = s.text.strip().upper()
            break

    journal_title = None
    sources_dc = _dc_text(meta, "source")
    if sources_dc:
        journal_title = sources_dc[0]

    abstract = None
    descriptions = _dc_text(meta, "description")
    if descriptions:
        abstract = descriptions[0]

    return Article(
        title=title,
        title_alt=titles[1] if len(titles) > 1 else None,
        abstract=abstract,
        keywords=_dc_text(meta, "subject"),
        authors=authors,
        journal_title=journal_title,
        issn=issn,
        volume=None,
        issue=None,
        pages=None,
        year=year,
        pub_date=pub_date,
        lang=lang or "es",
        url=url,
        source="redalyc",
        source_id=source_id,
        doi=doi,
        access="oa",
    )


def harvest(http, date_from: str, max_articles: int = 300,
            resumption_token: str | None = None,
            sets: list[str] | None = None) -> list[Article]:
    """Cosecha registros de Redalyc vía OAI-PMH (con soporte de sets por revista)."""
    ok, detail, base_url = test_availability(http)
    if not ok:
        raise SourceUnavailable(f"Redalyc no disponible: {detail}")

    out: list[Article] = []

    # Si se especifican sets (ISSNs de revistas de comunicación), cosechar por set
    target_sets = [s for s in (sets or []) if s and _ISSN_RE.match(s.strip())]
    if target_sets:
        budget_per_set = max(10, max_articles // len(target_sets))
        for s_issn in target_sets:
            if len(out) >= max_articles:
                break
            try:
                params = {
                    "verb": "ListRecords",
                    "metadataPrefix": "oai_dc",
                    "set": s_issn.strip(),
                }
                r = http.get(base_url, params=params, timeout=30)
                if r.status_code != 200 or "<error code=" in r.text:
                    continue
                root = ET.fromstring(r.text)
                count_set = 0
                for rec in root.findall(".//oai:record", _OAINS):
                    art = parse_record(rec)
                    if art:
                        if not art.issn:
                            art.issn = s_issn.strip().upper()
                        out.append(art)
                        count_set += 1
                    if len(out) >= max_articles or count_set >= budget_per_set:
                        break
            except Exception as e:
                log.debug("Redalyc set %s: %s", s_issn, e)
                continue
            time.sleep(config.REQUEST_DELAY)
        return out

    # Cosecha general con resumptionToken
    token = resumption_token
    while len(out) < max_articles:
        params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
        if token:
            params = {"verb": "ListRecords", "resumptionToken": token}
        else:
            params["from"] = f"{date_from}T00:00:00Z"
        try:
            r = http.get(base_url, params=params, timeout=45)
            r.raise_for_status()
        except Exception as e:
            log.warning("ListRecords falló: %s", e)
            break
        root = ET.fromstring(r.text)
        for rec in root.findall(".//oai:record", _OAINS):
            art = parse_record(rec)
            if art:
                out.append(art)
            if len(out) >= max_articles:
                break
        rt = root.find(".//oai:resumptionToken", _OAINS)
        token = rt.text.strip() if rt is not None and (rt.text or "").strip() else None
        if not token:
            break
        time.sleep(config.REQUEST_DELAY)
    return out