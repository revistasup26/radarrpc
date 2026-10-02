from radar.matching import parse_keywords, match_article

def test_parse_keywords():
    kws = parse_keywords("ciencia transmedia, periodismo; digital-media")
    assert "ciencia transmedia" in kws
    assert "periodismo" in kws
    assert "digital-media" in kws

def test_match_article():
    art = {"title": "Ciencia transmedia", "keywords": ["periodismo"], "abstract": ""}
    score = match_article(art, ["transmedia"])
    assert score["score"] > 0
    assert any(m["keyword"] == "transmedia" for m in score["matched"])
