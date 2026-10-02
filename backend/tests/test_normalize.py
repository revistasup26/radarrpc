from radar.normalize import norm

def test_normalize():
    assert norm("comunicación") == "comunicacion"
    assert norm("comunicação") == "comunicacao"
    # The norm function also removes html, or unescape does, let's just check accents
    assert norm("Héllo Wórld") == "hello world"
