import json
import os
from dataclasses import dataclass
from typing import Optional, Tuple


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _get_namespaces() -> Optional[Tuple[str, ...]]:
    raw_value = os.getenv("KUBE_NAMESPACES_ONLY", "").strip()
    if not raw_value:
        return None

    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            namespaces = [str(item).strip() for item in parsed if str(item).strip()]
            return tuple(namespaces) or None
    except json.JSONDecodeError:
        pass

    namespaces = [item.strip() for item in raw_value.split(",") if item.strip()]
    return tuple(namespaces) or None


@dataclass(frozen=True)
class Settings:
    teams_webhook_url: str
    webhook_format: str
    kube_use_cluster: bool
    kube_use_kubeconfig: bool
    kubeconfig_path: Optional[str]
    kube_context: Optional[str]
    namespaces_only: Optional[Tuple[str, ...]]
    flood_expire_ms: int
    recovery_alert: bool
    watch_timeout_seconds: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        teams_webhook_url = os.getenv("TEAMS_WEBHOOK_URL", "").strip()
        if not teams_webhook_url:
            raise ValueError("TEAMS_WEBHOOK_URL is required")

        return cls(
            teams_webhook_url=teams_webhook_url,
            webhook_format=os.getenv("WEBHOOK_FORMAT", "power_automate").strip().lower(),
            kube_use_cluster=_get_bool("KUBE_USE_CLUSTER", True),
            kube_use_kubeconfig=_get_bool("KUBE_USE_KUBECONFIG", False),
            kubeconfig_path=os.getenv("KUBECONFIG"),
            kube_context=os.getenv("KUBE_CONTEXT"),
            namespaces_only=_get_namespaces(),
            flood_expire_ms=_get_int("FLOOD_EXPIRE", 60000),
            recovery_alert=_get_bool("RECOVERY_ALERT", True),
            watch_timeout_seconds=_get_int("WATCH_TIMEOUT_SECONDS", 300),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
