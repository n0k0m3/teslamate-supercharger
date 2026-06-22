from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigError(Exception):
    pass


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise ConfigError(f"Required environment variable {name!r} is not set")
    return val


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"Environment variable {name!r} must be an integer, got {raw!r}")


@dataclass
class Config:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_pass: str

    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str

    encryption_key: str

    api_fetch_delay_seconds: int
    session_match_window_minutes: int

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            db_host=_require("DATABASE_HOST"),
            db_port=_int("DATABASE_PORT", 5432),
            db_name=_optional("DATABASE_NAME", "teslamate"),
            db_user=_optional("DATABASE_USER", "teslamate"),
            db_pass=_require("DATABASE_PASS"),
            mqtt_host=_optional("MQTT_HOST", "mosquitto"),
            mqtt_port=_int("MQTT_PORT", 1883),
            mqtt_username=_optional("MQTT_USERNAME"),
            mqtt_password=_optional("MQTT_PASSWORD"),
            encryption_key=_require("ENCRYPTION_KEY"),
            api_fetch_delay_seconds=_int("API_FETCH_DELAY_SECONDS", 30),
            session_match_window_minutes=_int("SESSION_MATCH_WINDOW_MINUTES", 15),
        )
