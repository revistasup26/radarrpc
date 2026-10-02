import pytest
from fastapi.testclient import TestClient
from radar.api.main import app
from radar import db

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def memory_db():
    conn = db.connect(":memory:")
    db.init_db(conn)
    yield conn
    conn.close()
