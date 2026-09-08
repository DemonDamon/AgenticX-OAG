"""Graph layer: record models, AGE store backend, entity resolution (P04).

Core symbols (records) import only pydantic. ``AGEGraphStore`` requires the
``[graph]`` extra (asyncpg) and ``EntityResolver`` the ``[ingest]`` extra
(numpy); both are re-exported lazily so a core install never pulls them in.
"""

from agenticx_oag.graph.records import LinkRecord, ObjectRecord, ProvInfo

__all__ = [
    "AGEGraphStore",
    "EntityResolver",
    "LinkRecord",
    "ObjectRecord",
    "ProvInfo",
]

_LAZY_EXPORTS: dict[str, str] = {
    "AGEGraphStore": "agenticx_oag.graph.age_store",
    "EntityResolver": "agenticx_oag.graph.resolve",
}


def __getattr__(name: str) -> object:
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_path)
    attribute = getattr(module, name)
    globals()[name] = attribute
    return attribute
