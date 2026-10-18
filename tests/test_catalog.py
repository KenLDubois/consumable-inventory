def test_default_home_location_exists(client):
    assert [loc["name"] for loc in client.get("/locations").json()] == ["home"]


def test_create_location(client):
    response = client.post("/locations", json={"name": "pantry"})

    assert response.status_code == 201
    assert response.json()["name"] == "pantry"


def test_duplicate_location_is_rejected(client):
    client.post("/locations", json={"name": "pantry"})

    assert client.post("/locations", json={"name": "pantry"}).status_code == 409


def test_create_and_get_item(client):
    response = client.post(
        "/items", json={"name": "Rice", "unit": "bag", "min_level": 1, "max_level": 3}
    )
    assert response.status_code == 201
    created = response.json()

    fetched = client.get(f"/items/{created['id']}").json()

    assert fetched == created
    assert fetched["unit"] == "bag"
    assert fetched["min_level"] == 1
    assert fetched["max_level"] == 3


def test_item_defaults(client, item):
    assert item["unit"] == "jar"
    assert item["min_level"] is None
    assert item["max_level"] is None


def test_duplicate_item_is_rejected(client, item):
    assert client.post("/items", json={"name": "Peanut butter"}).status_code == 409


def test_min_above_max_is_rejected(client):
    response = client.post("/items", json={"name": "Rice", "min_level": 4, "max_level": 2})

    assert response.status_code == 422


def test_update_item_levels(client, item):
    response = client.patch(f"/items/{item['id']}", json={"min_level": 1, "max_level": 2})

    assert response.status_code == 200
    assert response.json()["min_level"] == 1
    assert response.json()["max_level"] == 2
    assert response.json()["name"] == "Peanut butter"


def test_update_rejects_min_above_existing_max(client, item):
    client.patch(f"/items/{item['id']}", json={"max_level": 2})

    assert client.patch(f"/items/{item['id']}", json={"min_level": 3}).status_code == 422


def test_update_can_clear_a_level(client, item):
    client.patch(f"/items/{item['id']}", json={"max_level": 2})

    response = client.patch(f"/items/{item['id']}", json={"max_level": None})

    assert response.json()["max_level"] is None


def test_missing_item_is_404(client):
    assert client.get("/items/999").status_code == 404
    assert client.patch("/items/999", json={"unit": "jar"}).status_code == 404


def test_items_listed_by_name(client):
    for name in ["Rice", "Coffee", "Peanut butter"]:
        client.post("/items", json={"name": name})

    names = [i["name"] for i in client.get("/items").json()]

    assert names == ["Coffee", "Peanut butter", "Rice"]
