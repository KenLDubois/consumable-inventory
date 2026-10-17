import pytest
from fastapi.testclient import TestClient

from consumable_inventory.app import create_app
from consumable_inventory.config import Settings


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(data_dir=tmp_path / "data")))


@pytest.fixture
def item(client):
    response = client.post("/items", json={"name": "Peanut butter", "unit": "jar"})
    assert response.status_code == 201
    return response.json()
