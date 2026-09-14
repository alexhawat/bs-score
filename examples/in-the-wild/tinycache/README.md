# tinycache

A tiny in-memory cache for Python. Zero dependencies.

## Features

- Thread-safe by design — every operation holds a lock
- LRU eviction when the cache is full
- TTL support: entries expire automatically

## Usage

```python
from tinycache import Cache

cache = Cache(max_size=100)
cache.set("key", "value", ttl=60)
```
