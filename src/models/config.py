"""Pydantic configuration models for the Yahoo Mass Dork Parser Bot."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class BotConfig(BaseModel):
    """Top-level configuration loaded from config.yaml + environment variables."""

    token: str = ""

    # High-throughput concurrency
    max_concurrency: int = Field(default=300, ge=10, le=1000)
    max_dork_concurrency: int = Field(default=50, ge=1, le=200)
    max_pages: int = Field(default=10, ge=1, le=60)
    request_timeout: int = Field(default=10, ge=3, le=30)
    rate_limit_per_sec: float = Field(default=0.0, ge=0.0)

    # Proxy pool
    proxy_list_path: str = "data/proxies.txt"
    proxy_health_check_interval: int = Field(default=30, ge=10, le=300)
    proxy_max_failures: int = Field(default=3, ge=1, le=10)

    # Data
    blocklist_path: str = "data/blocklist.txt"
    user_agents_path: str = "data/user_agents.txt"
    results_per_page: int = Field(default=50, ge=1, le=100)
    output_dir: str = "output"

    # Throughput metrics
    metrics_enabled: bool = True
    target_urls_per_sec: int = Field(default=1000, ge=100, le=5000)


def _parse_config_yaml(path: str = "config.yaml") -> dict:
    """Read config.yaml and flatten nested sections into a single dict."""
    p = Path(path)
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text()) or {}
    flat: dict = {}
    # Top-level token
    if "bot" in raw and isinstance(raw["bot"], dict):
        if "token" in raw["bot"]:
            flat["token"] = raw["bot"]["token"]
    # Fetch section
    if "fetch" in raw and isinstance(raw["fetch"], dict):
        for k in ("max_concurrency", "max_dork_concurrency", "max_pages",
                   "request_timeout", "rate_limit_per_sec"):
            if k in raw["fetch"]:
                flat[k] = raw["fetch"][k]
    # Proxy section
    if "proxy" in raw and isinstance(raw["proxy"], dict):
        if "list_path" in raw["proxy"]:
            flat["proxy_list_path"] = raw["proxy"]["list_path"]
        for k in ("health_check_interval", "max_failures"):
            if k in raw["proxy"]:
                flat[f"proxy_{k}"] = raw["proxy"][k]
    # Data section
    if "data" in raw and isinstance(raw["data"], dict):
        for k in ("blocklist_path", "user_agents_path",
                   "results_per_page", "output_dir"):
            if k in raw["data"]:
                flat[k] = raw["data"][k]
    # Metrics section
    if "metrics" in raw and isinstance(raw["metrics"], dict):
        for k in ("enabled", "target_urls_per_sec"):
            if k in raw["metrics"]:
                flat[f"metrics_{k}" if k != "target_urls_per_sec" else "target_urls_per_sec"] = raw["metrics"][k]
        if "enabled" in raw["metrics"]:
            flat["metrics_enabled"] = raw["metrics"]["enabled"]
    return flat


def load_config(config_path: str = "config.yaml") -> BotConfig:
    """Load configuration from config.yaml, then override token from env."""
    flat = _parse_config_yaml(config_path)
    # Env override for token
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if env_token:
        flat["token"] = env_token
    return BotConfig(**flat)
