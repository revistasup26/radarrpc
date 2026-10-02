def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_cfp(client):
    response = client.get("/api/cfp")
    assert response.status_code == 200
    assert "journal" in response.json()
