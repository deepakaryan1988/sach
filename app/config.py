import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

load_dotenv()


class Config:
    _instance: Optional["Config"] = None
    _config: dict = {}

    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self) -> None:
        config_path = Path(__file__).parent.parent / "config.yaml"
        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)
        self._resolve_env_vars(self._config)

    def _resolve_env_vars(self, config: dict) -> None:
        for key, value in config.items():
            if isinstance(value, dict):
                self._resolve_env_vars(value)
            elif (
                isinstance(value, str)
                and value.startswith("${")
                and value.endswith("}")
            ):
                env_var = value[2:-1]
                val = os.getenv(env_var, "").strip()
                # Remove quotes if present
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                config[key] = val.strip()

    @property
    def ollama_base_url(self) -> str:
        return self._config["ollama"]["base_url"]

    @property
    def ollama_model(self) -> str:
        return self._config["ollama"]["model"]

    @property
    def openrouter_api_key(self) -> str:
        return self._config["openrouter"]["api_key"]

    @property
    def openrouter_base_url(self) -> str:
        return self._config["openrouter"]["base_url"]

    @property
    def openrouter_model(self) -> str:
        return self._config["openrouter"].get("model") or "meta-llama/llama-3.3-70b-instruct:free"

    @property
    def retrieval_index_path(self) -> str:
        return self._config["retrieval"]["index_path"]

    @property
    def retrieval_top_k(self) -> int:
        return self._config["retrieval"]["top_k"]

    @property
    def app_host(self) -> str:
        return self._config["app"]["host"]

    @property
    def app_port(self) -> int:
        return self._config["app"]["port"]

    @property
    def nvidia_api_key(self) -> str:
        return self._config.get("nvidia", {}).get("api_key", "")

    @property
    def nvidia_base_url(self) -> str:
        return self._config.get("nvidia", {}).get("base_url", "https://integrate.api.nvidia.com/v1")

    @property
    def openrouter_swarm(self) -> str:
        return self._config.get("models", {}).get("openrouter_swarm", "")

    @property
    def nvidia_swarm(self) -> str:
        return self._config.get("models", {}).get("nvidia_swarm", "")


def get_config() -> Config:
    return Config()
