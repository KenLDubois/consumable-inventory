def home_id(client):
    return next(loc["id"] for loc in client.get("/locations").json() if loc["name"] == "home")


def observe(client, item_id, quantity, **extra):
    response = client.post(
        "/observations", json={"item_id": item_id, "quantity": quantity, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_observation_defaults_to_home_location(client, item):
    obs = observe(client, item["id"], 2)

    assert obs["location_id"] == home_id(client)
    assert obs["source"] == "manual"


def test_observation_with_unknown_location(client, item):
    obs = observe(client, item["id"], 2, location_id=None)

    assert obs["location_id"] is None


def test_observation_for_missing_item_or_location_is_404(client, item):
    assert client.post("/observations", json={"item_id": 999, "quantity": 1}).status_code == 404
    response = client.post(
        "/observations", json={"item_id": item["id"], "quantity": 1, "location_id": 999}
    )
    assert response.status_code == 404


def test_negative_quantity_is_rejected(client, item):
    response = client.post("/observations", json={"item_id": item["id"], "quantity": -1})

    assert response.status_code == 422


def stock(client, item_id, as_of="2026-10-08T09:00:00Z"):
    return client.get(f"/items/{item_id}/stock", params={"as_of": as_of}).json()


def test_observation_shows_up_in_stock(client, item):
    observe(client, item["id"], 2)

    stock = client.get(f"/items/{item['id']}/stock").json()

    assert stock["on_hand"] == 2
    assert stock["locations"][0]["location_id"] == home_id(client)


def test_newer_reading_replaces_older_one(client, item):
    observe(client, item["id"], 3, observed_at="2026-10-01T09:00:00Z")
    observe(client, item["id"], 1, observed_at="2026-10-08T09:00:00Z")

    assert stock(client, item["id"])["on_hand"] == 1


def test_late_arriving_older_reading_does_not_replace_newer(client, item):
    observe(client, item["id"], 1, observed_at="2026-10-08T09:00:00Z")
    observe(client, item["id"], 3, observed_at="2026-10-01T09:00:00Z")

    assert stock(client, item["id"])["on_hand"] == 1


def test_readings_in_different_locations_add_up(client, item):
    garage = client.post("/locations", json={"name": "garage"}).json()
    observe(client, item["id"], 2)
    observe(client, item["id"], 1, location_id=garage["id"])

    assert client.get(f"/items/{item['id']}/stock").json()["on_hand"] == 3


def test_unknown_location_reading_can_raise_stock(client, item):
    observe(client, item["id"], 2, observed_at="2026-10-08T08:00:00Z")
    observe(client, item["id"], 5, location_id=None, observed_at="2026-10-08T08:30:00Z")

    assert stock(client, item["id"])["on_hand"] == 5


def test_unknown_location_reading_cannot_lower_stock(client, item):
    observe(client, item["id"], 2, observed_at="2026-10-08T08:00:00Z")
    observe(client, item["id"], 1, location_id=None, observed_at="2026-10-08T08:30:00Z")

    result = stock(client, item["id"])

    assert result["on_hand"] == 2
    assert [loc["quantity"] for loc in result["locations"]] == [2]


def test_timestamps_with_offsets_are_compared_in_utc(client, item):
    # 08:00 at -05:00 is 13:00 UTC, so it is newer than 12:00 UTC.
    observe(client, item["id"], 4, observed_at="2026-10-08T12:00:00Z")
    observe(client, item["id"], 1, observed_at="2026-10-08T08:00:00-05:00")

    assert stock(client, item["id"], as_of="2026-10-08T13:00:00Z")["on_hand"] == 1


def test_list_observations_newest_first(client, item):
    observe(client, item["id"], 3, observed_at="2026-10-01T09:00:00Z")
    observe(client, item["id"], 1, observed_at="2026-10-08T09:00:00Z")

    quantities = [o["quantity"] for o in client.get(f"/observations?item_id={item['id']}").json()]

    assert quantities == [1, 3]


def test_record_and_list_events(client, item):
    response = client.post(
        "/events", json={"item_id": item["id"], "kind": "purchase", "quantity": 2}
    )
    assert response.status_code == 201
    assert response.json()["location_id"] == home_id(client)

    events = client.get(f"/events?item_id={item['id']}").json()

    assert [(e["kind"], e["quantity"]) for e in events] == [("purchase", 2)]


def test_event_kind_and_quantity_are_validated(client, item):
    bad_kind = {"item_id": item["id"], "kind": "gift", "quantity": 1}
    zero = {"item_id": item["id"], "kind": "use", "quantity": 0}

    assert client.post("/events", json=bad_kind).status_code == 422
    assert client.post("/events", json=zero).status_code == 422


def test_data_survives_restart(tmp_path):
    from fastapi.testclient import TestClient

    from consumable_inventory.app import create_app
    from consumable_inventory.config import Settings

    settings = Settings(data_dir=tmp_path / "data")
    TestClient(create_app(settings)).post("/items", json={"name": "Rice"})

    items = TestClient(create_app(settings)).get("/items").json()

    assert [i["name"] for i in items] == ["Rice"]
