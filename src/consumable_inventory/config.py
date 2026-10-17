"""Runtime settings, read from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    # Where the database and stored photos live. Mounted as a volume in Docker.
    data_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(data_dir=Path(os.environ.get("INVENTORY_DATA_DIR", "./data")))
