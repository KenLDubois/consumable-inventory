def add_item(client, name, min_level=None, max_level=None):
    body = {"name": name, "min_level": min_level, "max_level": max_level}
    return client.post("/items", json=body).json()


def observe(client, item_id, quantity, at):
    response = client.post(
        "/observations", json={"item_id": item_id, "quantity": quantity, "observed_at": at}
    )
    assert response.status_code == 201


def shopping_list(client, **params):
    response = client.get("/list", params={"as_of": "2026-10-08T09:00:00Z", **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_catalog_gives_empty_list(client):
    assert shopping_list(client)["lines"] == []


def test_low_item_is_listed_and_full_item_is_not(client):
    pb = add_item(client, "Peanut butter", min_level=1, max_level=3)
    rice = add_item(client, "Rice", min_level=1, max_level=2)
    observe(client, pb["id"], 0, "2026-10-08T08:00:00Z")
    observe(client, rice["id"], 2, "2026-10-08T08:00:00Z")

    lines = shopping_list(client)["lines"]

    assert [(line["name"], line["quantity"]) for line in lines] == [("Peanut butter", 3)]
    assert lines[0]["reason"]


def test_default_shopping_date_is_a_week_out(client):
    result = shopping_list(client)

    assert result["next_shop"].startswith("2026-10-15T09:00:00")


def test_usage_until_a_later_shopping_date_is_counted(client):
    pb = add_item(client, "Peanut butter", min_level=1, max_level=3)
    observe(client, pb["id"], 3, "2026-10-01T09:00:00Z")
    observe(client, pb["id"], 2, "2026-10-08T09:00:00Z")

    soon = shopping_list(client, next_shop="2026-10-09T09:00:00Z")["lines"]
    later = shopping_list(client, next_shop="2026-10-29T09:00:00Z")["lines"]

    assert soon == []
    assert [line["quantity"] for line in later] == [3]


def test_shopping_date_in_the_past_is_rejected(client):
    response = client.get(
        "/list", params={"as_of": "2026-10-08T09:00:00Z", "next_shop": "2026-10-01T09:00:00Z"}
    )

    assert response.status_code == 422


def test_stock_reports_usage_rate(client):
    pb = add_item(client, "Peanut butter")
    observe(client, pb["id"], 3, "2026-10-01T09:00:00Z")
    observe(client, pb["id"], 2, "2026-10-08T09:00:00Z")

    stock = client.get(f"/items/{pb['id']}/stock", params={"as_of": "2026-10-08T09:00:00Z"})

    assert stock.json()["usage_per_day"] == 1 / 7
    assert stock.json()["on_hand"] == 2
