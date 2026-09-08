"""Ontology core: Pydantic mirror of the proto contract, YAML IO, OWL export, SHACL validation.

Core symbols (model, errors, YAML IO) import only pydantic/pyyaml. The RDF
symbols (``to_turtle`` / ``to_jsonld`` / ``build_shapes`` / ``validate_graph``)
are re-exported lazily so that a core install never requires rdflib/pyshacl
(NFR-2); they are provided by the ``[owl]`` extra.
"""

from agenticx_oag.ontology.errors import OntologyError, OntologyValidationError
from agenticx_oag.ontology.io import dump_ontology, load_ontology, to_yaml
from agenticx_oag.ontology.model import (
    ActionType,
    Cardinality,
    DataType,
    LinkType,
    ObjectType,
    Ontology,
    PropertyType,
)

__all__ = [
    "ActionType",
    "Cardinality",
    "DataType",
    "LinkType",
    "ObjectType",
    "Ontology",
    "OntologyError",
    "OntologyValidationError",
    "PropertyType",
    "build_shapes",
    "dump_ontology",
    "load_ontology",
    "to_jsonld",
    "to_turtle",
    "to_yaml",
    "validate_graph",
]

_LAZY_EXPORTS: dict[str, str] = {
    "to_turtle": "agenticx_oag.ontology.owl_export",
    "to_jsonld": "agenticx_oag.ontology.owl_export",
    "build_shapes": "agenticx_oag.ontology.shacl",
    "validate_graph": "agenticx_oag.ontology.shacl",
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
