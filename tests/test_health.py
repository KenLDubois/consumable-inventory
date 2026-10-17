from fastapi.testclient import TestClient

from consumable_inventory import __version__
from consumable_inventory.app import create_app
from consumable_inventory.config import Settings


def test_health_reports_ok_and_version(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "data")))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_app_creates_data_dir(tmp_path):
    data_dir = tmp_path / "nested" / "data"

    create_app(Settings(data_dir=data_dir))

    assert data_dir.is_dir()
