"""Run the service: `python -m consumable_inventory` or `consumable-inventory`."""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "consumable_inventory.app:create_app",
        factory=True,
        host=os.environ.get("INVENTORY_HOST", "0.0.0.0"),
        port=int(os.environ.get("INVENTORY_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
