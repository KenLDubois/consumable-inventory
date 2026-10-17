# Consumable Inventory

Self-hosted tracking of household consumables: what's on hand, what's running low, and what to buy.

The goal is a weekly shopping list built with as little manual effort as possible. Phone photos,
fixed sensors (scales, cameras) and purchase records all feed one stock estimate per item, and the
list is built from that estimate and each item's minimum and maximum levels.

**Status:** early development. The first milestone is a proof of value: photograph a pantry shelf,
photograph it again a week later, and get a correct shopping list from the difference.

## Design principles

- **Self-hostable.** One service in one Docker container, with a SQLite database.
- **Extensible.** Everything goes through a public API with two doors: send an observation in,
  read the shopping list out. New sensors and exports plug into those doors.
- **Vendor-agnostic AI.** The AI only reads photos, behind one swappable interface. Stock math and
  list building are plain, testable code.

## Running it

With Docker:

```sh
docker compose up -d --build
curl http://localhost:8000/health
```

Data (the database and stored photos) lives in `./data`, mounted into the container at `/data`.

For development:

```sh
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
consumable-inventory   # serves on http://localhost:8000
```

### Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `INVENTORY_DATA_DIR` | `./data` (`/data` in Docker) | Where the database and photos are stored |
| `INVENTORY_HOST` | `0.0.0.0` | Address to listen on |
| `INVENTORY_PORT` | `8000` | Port to listen on |

## License

MIT
