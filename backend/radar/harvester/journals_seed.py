"""Lista semilla de revistas iberoamericanas de Ciencias de la Comunicación.

El MVP arranca con esta red curada (~70 revistas) y se AUTO-EXPANDE en cada
cosecha con el descubrimiento de revistas de Comunicación en SciELO (por área
temática) y con nuevos ISSN detectados vía Crossref. La meta de 300+ revistas
se alcanza de forma incremental. Fuentes de referencia: SciELO, Redalyc,
Latindex, MIAR, DOAJ.
"""

SEED_JOURNALS: list[dict] = [
    # --- Revista ancla (corpus canónico del radar) ---
    {"title": "Revista Panamericana de Comunicación", "issn_print": "2683-2208", "issn_online": "2683-2208", "country": "MX"},
    # --- España ---
    {"title": "Comunicar", "issn_print": "1134-3478", "issn_online": "1988-3293", "country": "ES"},
    {"title": "El Profesional de la Información", "issn_print": "1386-6710", "issn_online": "1699-2407", "country": "ES"},
    {"title": "Revista Latina de Comunicación Social", "issn_print": "1138-5820", "issn_online": "1138-5820", "country": "ES"},
    {"title": "Zer: Revista de Estudios de Comunicación", "issn_print": "1137-1102", "issn_online": "1989-631X", "country": "ES"},
    {"title": "Razón y Palabra", "issn_print": "1605-4806", "issn_online": "1605-4806", "country": "EC"},
    {"title": "Comunicación y Sociedad (España)", "issn_print": "0214-0039", "issn_online": "2174-0895", "country": "ES"},
    {"title": "Estudios sobre el Mensaje Periodístico", "issn_print": "1134-1629", "issn_online": "1988-2696", "country": "ES"},
    {"title": "Historia y Comunicación Social", "issn_print": "1137-0734", "issn_online": "1988-3056", "country": "ES"},
    {"title": "Ámbitos. Revista Internacional de Comunicación", "issn_print": "1139-1979", "issn_online": "1988-5733", "country": "ES"},
    {"title": "adComunica. Revista Científica de Estrategias, Tendencias e Innovación en Comunicación", "issn_print": "2174-0992", "issn_online": "2254-2728", "country": "ES"},
    {"title": "Miguel Hernández Communication Journal", "issn_print": "1989-8681", "issn_online": "1989-8681", "country": "ES"},
    {"title": "Icono 14", "issn_print": "1697-8293", "issn_online": "1697-8293", "country": "ES"},
    {"title": "Doxa Comunicación", "issn_print": "1696-019X", "issn_online": "2386-3978", "country": "ES"},
    {"title": "Anàlisi: Quaderns de Comunicació i Cultura", "issn_print": "0211-2175", "issn_online": "2340-5236", "country": "ES"},
    {"title": "Tripodos", "issn_print": "1138-3305", "issn_online": "2340-5007", "country": "ES"},
    {"title": "Communication & Society", "issn_print": "0214-0039", "issn_online": "2386-7876", "country": "ES"},
    {"title": "Index.comunicación", "issn_print": "2174-1859", "issn_online": "2174-1859", "country": "ES"},
    {"title": "Fonseca, Journal of Communication", "issn_print": "2172-9077", "issn_online": "2172-9077", "country": "ES"},
    {"title": "Vivat Academia", "issn_print": "1575-2844", "issn_online": "1575-2844", "country": "ES"},
    {"title": "Revista Mediterránea de Comunicación", "issn_print": "1989-872X", "issn_online": "1989-872X", "country": "ES"},
    # --- México ---
    {"title": "Comunicación y Sociedad (México)", "issn_print": "0188-252X", "issn_online": "2448-9042", "country": "MX"},
    {"title": "Revista Mexicana de Comunicación", "issn_print": "0187-9219", "issn_online": "0187-9219", "country": "MX"},
    {"title": "Virtualis", "issn_print": "2007-2678", "issn_online": "2007-2678", "country": "MX"},
    {"title": "Global Media Journal México", "issn_print": "2007-2031", "issn_online": "1550-7521", "country": "MX"},
    {"title": "Revista Mexicana de Opinión Pública", "issn_print": "1870-7300", "issn_online": "2448-4911", "country": "MX"},
    # --- Colombia ---
    {"title": "Palabra Clave", "issn_print": "0122-8285", "issn_online": "2027-534X", "country": "CO"},
    {"title": "Signo y Pensamiento", "issn_print": "0120-4823", "issn_online": "2027-2731", "country": "CO"},
    {"title": "Anagramas. Rumbos y Sentidos de la Comunicación", "issn_print": "1692-2522", "issn_online": "2248-4086", "country": "CO"},
    {"title": "Luciérnaga Comunicación", "issn_print": "2027-1557", "issn_online": "2027-1557", "country": "CO"},
    {"title": "Encuentros (Universidad Autónoma del Caribe)", "issn_print": "1692-5858", "issn_online": "2322-9415", "country": "CO"},
    {"title": "Comunicación y Ciudadanía", "issn_print": "2027-6287", "issn_online": "2027-6287", "country": "CO"},
    # --- Brasil ---
    {"title": "Intercom: Revista Brasileira de Ciências da Comunicação", "issn_print": "1809-5844", "issn_online": "1980-3508", "country": "BR"},
    {"title": "E-Compós", "issn_print": "1808-2599", "issn_online": "1808-2599", "country": "BR"},
    {"title": "Galáxia (São Paulo)", "issn_print": "1519-311X", "issn_online": "1982-2553", "country": "BR"},
    {"title": "MATRIZes", "issn_print": "1982-2073", "issn_online": "1982-8160", "country": "BR"},
    {"title": "Revista Famecos: Mídia, Cultura e Tecnologia", "issn_print": "1415-0549", "issn_online": "1980-3729", "country": "BR"},
    {"title": "Comunicação & Sociedade (São Bernardo do Campo)", "issn_print": "0101-2657", "issn_online": "2175-7755", "country": "BR"},
    {"title": "Líbero", "issn_print": "1517-6105", "issn_online": "1984-692X", "country": "BR"},
    {"title": "InTexto", "issn_print": "1807-8583", "issn_online": "1807-8583", "country": "BR"},
    {"title": "Comunicação Mídia e Consumo", "issn_print": "1806-4981", "issn_online": "1983-7070", "country": "BR"},
    {"title": "Brazilian Journalism Research", "issn_print": "1808-4079", "issn_online": "1981-9854", "country": "BR"},
    {"title": "Signos do Consumo", "issn_print": "1984-5057", "issn_online": "1984-5057", "country": "BR"},
    {"title": "RuMoRes", "issn_print": "1981-4070", "issn_online": "1981-4070", "country": "BR"},
    {"title": "Ação Midiática", "issn_print": "2238-0701", "issn_online": "2238-0701", "country": "BR"},
    {"title": "ESFERAS", "issn_print": "2446-6190", "issn_online": "2446-6190", "country": "BR"},
    # --- Chile ---
    {"title": "Cuadernos.info", "issn_print": "0719-367X", "issn_online": "0719-3661", "country": "CL"},
    {"title": "Comunicación y Medios", "issn_print": "0716-3991", "issn_online": "0719-1529", "country": "CL"},
    {"title": "Perspectivas de la Comunicación", "issn_print": "0718-4867", "issn_online": "0718-4867", "country": "CL"},
    # --- Argentina ---
    {"title": "Cuadernos del Centro de Estudios en Diseño y Comunicación", "issn_print": "1668-0227", "issn_online": "1853-3523", "country": "AR"},
    {"title": "Question/Cuestión", "issn_print": "1669-6581", "issn_online": "1669-6581", "country": "AR"},
    {"title": "Austral Comunicación", "issn_print": "2313-9129", "issn_online": "2313-9137", "country": "AR"},
    {"title": "InMediaciones de la Comunicación", "issn_print": "1510-5091", "issn_online": "1688-8626", "country": "UY"},
    {"title": "Avatares de la Comunicación y la Cultura", "issn_print": "1853-5925", "issn_online": "1853-5925", "country": "AR"},
    {"title": "Oficios Terrestres", "issn_print": "1668-5431", "issn_online": "1853-3248", "country": "AR"},
    {"title": "La Trama de la Comunicación", "issn_print": "1668-5628", "issn_online": "2314-1204", "country": "AR"},
    {"title": "Tram(p)as de la Comunicación y la Cultura", "issn_print": "1668-5547", "issn_online": "2314-274X", "country": "AR"},
    {"title": "Intersecciones en Comunicación", "issn_print": "2250-4184", "issn_online": "2250-4184", "country": "AR"},
    # --- Ecuador ---
    {"title": "Chasqui. Revista Latinoamericana de Comunicación", "issn_print": "1390-1079", "issn_online": "1390-924X", "country": "EC"},
    {"title": "ComHumanitas: Revista Científica de Comunicación", "issn_print": "1390-776X", "issn_online": "1390-776X", "country": "EC"},
    # --- Perú ---
    {"title": "Contratexto", "issn_print": "1025-9945", "issn_online": "1993-4904", "country": "PE"},
    {"title": "Correspondencias & Análisis", "issn_print": "2224-235X", "issn_online": "2304-235X", "country": "PE"},
    {"title": "Revista de Comunicación (Universidad de Piura)", "issn_print": "1684-0933", "issn_online": "2227-1465", "country": "PE"},
    # --- Uruguay ---
    {"title": "dixit", "issn_print": "1688-3497", "issn_online": "0797-3695", "country": "UY"},
    # --- Bolivia ---
    {"title": "Punto Cero", "issn_print": "1815-0276", "issn_online": "2224-8838", "country": "BO"},
    # --- Venezuela ---
    {"title": "Anuario Electrónico de Estudios en Comunicación Social Disertaciones", "issn_print": "1856-9536", "issn_online": "1856-9536", "country": "VE"},
    {"title": "Comunicación. Estudios venezolanos de comunicación", "issn_print": "0798-1856", "issn_online": "2542-3301", "country": "VE"},
    # --- Portugal ---
    {"title": "Observatorio (OBS*)", "issn_print": "1646-5954", "issn_online": "1646-5954", "country": "PT"},
    {"title": "Comunicação e Sociedade", "issn_print": "1645-2089", "issn_online": "2183-3575", "country": "PT"},
    {"title": "Media & Jornalismo", "issn_print": "1645-5681", "issn_online": "2183-5462", "country": "PT"},
    {"title": "Estudos em Comunicação", "issn_print": "1646-4974", "issn_online": "1646-4974", "country": "PT"},
]