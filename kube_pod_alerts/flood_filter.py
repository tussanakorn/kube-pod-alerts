import time


class FloodFilter:
    def __init__(self, expire_ms: int) -> None:
        self.expire_ms = expire_ms
        self._store: dict[str, float] = {}

    def accept(self, key: str) -> bool:
        now_ms = time.time() * 1000
        expires_at = self._store.get(key)
        accepted = expires_at is None or expires_at <= now_ms
        self._store[key] = now_ms + self.expire_ms
        return accepted
