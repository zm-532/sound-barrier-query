from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REQUIRED_KEYS = ("BASE_URL", "API_KEY", "MODEL")


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str

    def is_complete(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


def load_llm_config(path: str | Path = ".env") -> LLMConfig:
    values = _read_env_file(path)
    return LLMConfig(
        base_url=values.get("BASE_URL", "").strip(),
        api_key=values.get("API_KEY", "").strip(),
        model=values.get("MODEL", "").strip(),
    )


def load_llm_values(path: str | Path = ".env") -> dict[str, str]:
    return _read_env_file(path)


def missing_keys(values: dict[str, str]) -> list[str]:
    return [key for key in REQUIRED_KEYS if not values.get(key, "").strip()]


def _read_env_file(path: str | Path) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        uppercase_env = env_path.with_name(".ENV")
        if uppercase_env.exists():
            env_path = uppercase_env
        else:
            return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values
