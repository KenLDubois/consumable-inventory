"""The web service. Every feature, including our own web page, goes through this API."""

from fastapi import FastAPI

from consumable_inventory import __version__
from consumable_inventory.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Consumable Inventory", version=__version__)
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app
