from pathlib import Path
from typing import Any

import yaml

from .models import Configuration


class ConfigurationLoader:
    """Loads C.O.R.E. configuration from YAML files."""

    def load(
        self,
        path: str | Path,
        environment: str = "development",
    ) -> Configuration:
        config_path = Path(path)

        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}"
            )

        if not config_path.is_file():
            raise ValueError(
                f"Configuration path is not a file: {config_path}"
            )

        with config_path.open("r", encoding="utf-8") as file:
            data: Any = yaml.safe_load(file)

        if data is None:
            data = {}

        if not isinstance(data, dict):
            raise ValueError(
                "Configuration root must be a mapping."
            )

        return Configuration(
            data=data,
            environment=environment,
        )
