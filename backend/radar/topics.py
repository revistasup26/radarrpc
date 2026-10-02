"""Ontología de campos de conocimiento en Ciencias de la Comunicación y clasificación temática."""
from __future__ import annotations

from .normalize import norm, word_variants

# Los 8 campos canónicos de las Ciencias de la Comunicación en el espacio iberoamericano
COMMUNICATION_FIELDS = [
    {
        "id": "ecologia_medios",
        "name": "Ecología de los Medios y Cultura Tecnológica",
        "name_pt": "Ecologia dos Meios e Cultura Tecnológica",
        "description": "El entorno mediático como ambiente cultural, interfaces, extensiones humanas, McLuhanismo e IA.",
        "keywords_es": [
            "ecología de los medios", "medio como mensaje", "entorno tecnológico", "extensión humana",
            "cultura digital", "inteligencia artificial", "algoritmos", "plataformas digitales",
            "metaverso", "realidad virtual", "marshall mcluhan", "mediatización", "tecnología y sociedad"
        ],
        "keywords_pt": [
            "ecologia dos meios", "meio como mensagem", "ambiente tecnológico", "extensão humana",
            "cultura digital", "inteligência artificial", "algoritmos", "plataformas digitais",
            "mediatização", "tecnologia e sociedade"
        ],
        "journals_focus": ["Revista Panamericana de Comunicación", "Comunicar", "Palabra Clave", "MATRIZes"],
    },
    {
        "id": "comunicacion_politica",
        "name": "Comunicación Política, Opinión Pública y Desinformación",
        "name_pt": "Comunicação Política, Opinião Pública e Desinformação",
        "description": "Campañas electorales, framing, polarización, desinformación, discurso del odio y esfera pública.",
        "keywords_es": [
            "comunicación política", "desinformación", "fake news", "polarización", "opinión pública",
            "campañas electorales", "propaganda", "discurso político", "democracia", "esfera pública",
            "redes sociales y política", "discurso de odio", "framing", "encuadres"
        ],
        "keywords_pt": [
            "comunicação política", "desinformação", "polarização", "opinião pública",
            "campanhas eleitorais", "propaganda", "discurso político", "democracia", "esfera pública",
            "redes sociais e política", "discurso de ódio"
        ],
        "journals_focus": ["Revista Latina de Comunicación Social", "Doxa Comunicación", "Opinião Pública"],
    },
    {
        "id": "periodismo_digital",
        "name": "Periodismo, Medios Digitales y Nuevas Narrativas",
        "name_pt": "Jornalismo, Mídias Digitais e Novas Narrativas",
        "description": "Rutinas periodísticas, verificación (fact-checking), pódcast, TikTok, narrativas móviles y modelos de negocio.",
        "keywords_es": [
            "periodismo digital", "periodismo", "fact-checking", "verificación", "redacciones",
            "narrativas periodísticas", "pódcast", "prensa", "tiktok y noticias", "medios locales",
            "periodismo de datos", "ciberperiodismo", "infomediación", "modelos de negocio"
        ],
        "keywords_pt": [
            "jornalismo digital", "jornalismo", "fact-checking", "verificação", "redações",
            "narrativas jornalísticas", "podcast", "imprensa", "jornalismo de dados", "ciberjornalismo"
        ],
        "journals_focus": ["Estudios sobre el Mensaje Periodístico", "Brazilian Journalism Research", "Cuadernos.info"],
    },
    {
        "id": "comunicacion_social_comunitaria",
        "name": "Comunicación Social, Comunitaria y Movimientos Ciudadanos",
        "name_pt": "Comunicação Social, Comunitária e Movimentos Cidadãos",
        "description": "Medios comunitarios, derechos humanos, comunicación para el cambio social, género y ciudadanía.",
        "keywords_es": [
            "comunicación social", "comunicación comunitaria", "cambio social", "movimientos sociales",
            "derechos humanos", "género y medios", "ciudadanía", "comunicación alternativa",
            "apropiación social", "comunicación popular", "indígena", "diversidad"
        ],
        "keywords_pt": [
            "comunicação social", "comunicação comunitária", "mudança social", "movimentos sociais",
            "direitos humanos", "gênero e mídia", "cidadania", "comunicação alternativa",
            "apropriação social", "comunicação popular"
        ],
        "journals_focus": ["Chasqui", "Signo y Pensamiento", "Intercom: Revista Brasileira de Ciências da Comunicação"],
    },
    {
        "id": "comunicacion_cientifica_salud",
        "name": "Comunicación Científica, Salud y Medio Ambiente",
        "name_pt": "Comunicação Científica, Saúde e Meio Ambiente",
        "description": "Divulgación científica, comunicación en salud pública, infodemia, cambio climático y comunicación de riesgos.",
        "keywords_es": [
            "comunicación científica", "divulgación científica", "comunicación en salud", "infodemia",
            "ciencia abierta", "medio ambiente", "cambio climático", "comunicación de riesgos",
            "periodismo científico", "percepción pública de la ciencia", "revistas científicas"
        ],
        "keywords_pt": [
            "comunicação científica", "divulgação científica", "comunicação em saúde", "infodemia",
            "ciência aberta", "meio ambiente", "mudança climática", "jornalismo científico",
            "revistas científicas"
        ],
        "journals_focus": ["Interface - Comunicação, Saúde, Educação", "El Profesional de la Información", "História, Ciências, Saúde-Manguinhos"],
    },
    {
        "id": "audiovisual_ficcion_transmedia",
        "name": "Comunicación Audiovisual, Cine y Ficción Transmedia",
        "name_pt": "Comunicação Audiovisual, Cinema e Ficção Transmídia",
        "description": "Cine, series de televisión, streaming, transmedia storytelling, videojuegos, estética y cultura audiovisual.",
        "keywords_es": [
            "comunicación audiovisual", "cine", "ficción televisiva", "series", "transmedia",
            "videojuegos", "narrativa transmedia", "streaming", "netflix", "estética audiovisual",
            "cultura visual", "animación", "guion"
        ],
        "keywords_pt": [
            "comunicação audiovisual", "cinema", "ficção televisiva", "séries", "transmídia",
            "videogames", "narrativa transmídia", "streaming", "estética audiovisual", "cultura visual"
        ],
        "journals_focus": ["adComunica", "L'Atalante", "Significação: Revista de Cultura Audiovisual"],
    },
    {
        "id": "comunicacion_organizacional",
        "name": "Comunicación Organizacional, Corporativa y Relaciones Públicas",
        "name_pt": "Comunicação Organizacional, Corporativa e Relações Públicas",
        "description": "Identidad corporativa, gestión de crisis, comunicación interna, reputación, marcas y publicidad.",
        "keywords_es": [
            "comunicación organizacional", "comunicación corporativa", "relaciones públicas", "reputación",
            "gestión de crisis", "identidad institucional", "marcas", "publicidad", "branding",
            "comunicación interna", "responsabilidad social corporativa", "stakeholders"
        ],
        "keywords_pt": [
            "comunicação organizacional", "comunicação corporativa", "relações públicas", "reputação",
            "gestão de crise", "identidade institucional", "marcas", "publicidade", "branding",
            "comunicação interna"
        ],
        "journals_focus": ["Revista Internacional de Relaciones Públicas", "Organicom"],
    },
    {
        "id": "educomunicacion_alfabetizacion",
        "name": "Educomunicación, Alfabetización Mediática y Juventud",
        "name_pt": "Educomunicação, Alfabetização Midiática e Juventude",
        "description": "Educación en medios, competencias digitales, consumos culturales juveniles y uso educativo de pantallas.",
        "keywords_es": [
            "educomunicación", "alfabetización mediática", "media literacy", "competencias digitales",
            "jóvenes y redes", "educación en medios", "audiencias infantiles", "tic en educación",
            "generación z", "prosumidores"
        ],
        "keywords_pt": [
            "educomunicação", "alfabetização midiática", "competências digitais",
            "jovens e redes", "educação em mídia", "audiências infantis", "geração z"
        ],
        "journals_focus": ["Comunicar", "Revista de Comunicación de la SEECI"],
    },
]


def classify_article_fields(art: dict) -> list[dict]:
    """Asigna los campos temáticos de la Comunicación a los que pertenece el artículo."""
    text = " ".join([
        norm(art.get("title") or ""),
        norm(art.get("abstract") or ""),
        " ".join(norm(k if isinstance(k, str) else k.get("k", "")) for k in (art.get("keywords") or []))
    ])
    if not text.strip():
        return []

    tokens = set(text.split())
    scored_fields = []

    for f in COMMUNICATION_FIELDS:
        score = 0
        matched_kws = []
        all_kws = f["keywords_es"] + f["keywords_pt"]
        for kw in all_kws:
            nkw = norm(kw)
            if " " in nkw:
                if nkw in text:
                    score += 3
                    matched_kws.append(kw)
            else:
                if nkw in tokens:
                    score += 1
                    matched_kws.append(kw)

        # Bonus si la revista está focalizada en este campo
        jt = norm(art.get("journal_title") or "")
        if any(norm(jf) in jt for jf in f["journals_focus"]):
            score += 4

        if score >= 3:
            scored_fields.append({
                "id": f["id"],
                "name": f["name"],
                "score": score,
                "matched_kws": list(dict.fromkeys(matched_kws))[:4],
            })

    scored_fields.sort(key=lambda x: -x["score"])
    return scored_fields[:2]
