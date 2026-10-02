from radar.citations import format_citation

def test_apa_citation():
    art = {
        "title": "Title",
        "authors": [{"family": "Smith", "given": "John"}],
        "year": 2023,
        "journal_title": "Journal of Testing",
        "volume": "1",
        "issue": "2",
        "pages": "10-20",
        "doi": "10.1234/test"
    }
    apa = format_citation(art, "apa")
    assert "Smith" in apa
    assert "2023" in apa
    assert "Title" in apa

def test_bibtex_citation():
    art = {
        "title": "Title",
        "authors": [{"family": "Smith", "given": "John"}],
        "year": 2023,
        "journal_title": "Journal of Testing",
        "doi": "10.1234/test"
    }
    bib = format_citation(art, "bibtex")
    assert "@article" in bib
    assert "Smith" in bib
