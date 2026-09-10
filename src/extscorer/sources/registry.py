"""Generic source registry: maps a `source_slug` to the concrete
`LeadDataSource` subclass that knows how to fetch it.

This is the mechanism that makes adding a new town's VGSI scraper, or a
new bulk dataset, "write one new source module," not "touch shared
code": a real source module (living downstream, e.g.
`extscorer_full.sources.<something>`) decorates its class with
`@register_source("some_source_slug")` at import time, and anything
holding a `source_slug` string (e.g. a `clients/<client_id>/config.yaml`
`targets:` entry) can resolve it to a runnable source via
`get_source_class` without ever importing that module by name. Mirrors
`oppscanner.scrapers.registry` exactly.

This module knows nothing about any real slug -- it ships in the public,
client-agnostic package.
"""
from __future__ import annotations

from extscorer.sources.base import LeadDataSource

_REGISTRY: dict[str, type[LeadDataSource]] = {}


def register_source(source_slug: str):
    """Class decorator: register `cls` as the source for `source_slug`.

    Raises `ValueError` on a conflicting duplicate slug rather than
    silently overwriting the earlier registration -- two source modules
    accidentally claiming the same slug is a bug worth surfacing loudly,
    not a last-import-wins ambiguity. Re-decorating the same class under
    the same slug (e.g. a module reimported) is not treated as a
    conflict.
    """

    def decorator(cls: type[LeadDataSource]) -> type[LeadDataSource]:
        existing = _REGISTRY.get(source_slug)
        if existing is not None and existing is not cls:
            raise ValueError(
                f"source_slug {source_slug!r} is already registered to "
                f"{existing.__qualname__!r}; cannot also register "
                f"{cls.__qualname__!r}."
            )
        _REGISTRY[source_slug] = cls
        return cls

    return decorator


def get_source_class(source_slug: str) -> type[LeadDataSource]:
    """Look up the source class registered for `source_slug`.

    Raises `KeyError` if nothing is registered -- e.g. a client config
    references a slug whose source module hasn't been written or
    imported yet.
    """
    try:
        return _REGISTRY[source_slug]
    except KeyError:
        raise KeyError(
            f"No source registered for source_slug {source_slug!r}. "
            "Make sure the module defining it (decorated with "
            "@register_source(...)) has been imported."
        ) from None


def registered_source_slugs() -> list[str]:
    """Every `source_slug` currently registered, for diagnostics/tests."""
    return sorted(_REGISTRY)


def _clear_registry_for_tests() -> None:
    """Reset the registry. Test-only -- real code should never call this."""
    _REGISTRY.clear()
