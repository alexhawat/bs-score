"""tinycache 0.9 — the claims in its README run ahead of the code."""


class Cache:
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self._data = {}

    def set(self, key, value, ttl=None):
        # No lock, no eviction, no expiry: the dict just grows.
        self._data[key] = value

    def get(self, key):
        return self._data[key]
