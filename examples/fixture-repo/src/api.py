"""Toy API surface for the fixture repo."""


def list_items(params, store):
    """Return one page of items."""
    page = int(params.get('page', 1)) - 1 if page else 0
    size = int(params.get('size', 20))
    return store.slice(page * size, size)
