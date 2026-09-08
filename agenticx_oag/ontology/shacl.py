"""SHACL shapes generation and instance-graph validation — ``[owl]`` extra (FR-7).

Every ObjectType becomes a ``sh:NodeShape`` targeting its class; each property
becomes a ``sh:PropertyShape`` carrying ``sh:datatype`` and ``sh:minCount 1``
when the property is required. Link-type properties are not shaped (they belong
to the instance layer managed by the graph store).
"""

from __future__ import annotations

from rdflib import RDF, RDFS, Graph, Literal, URIRef
from rdflib.namespace import SH
from pyshacl import validate

from agenticx_oag.ontology.model import Ontology
from agenticx_oag.ontology.owl_export import base_iri, class_iri, property_iri, xsd_datatype


def build_shapes_graph(ontology: Ontology) -> Graph:
    """Build the SHACL shapes graph for an ontology."""
    graph = Graph()
    graph.bind("oag", base_iri(ontology))
    graph.bind("sh", SH)

    for obj in ontology.object_types:
        cls = class_iri(ontology, obj.api_name)
        shape = URIRef(f"{cls}Shape")
        graph.add((shape, RDF.type, SH.NodeShape))
        graph.add((shape, SH.targetClass, cls))
        graph.add((shape, RDFS.label, Literal(f"{obj.display_name} node shape")))
        for prop in obj.properties:
            path = property_iri(ontology, obj.api_name, prop.api_name)
            prop_shape = URIRef(f"{path}Shape")
            graph.add((shape, SH.property, prop_shape))
            graph.add((prop_shape, RDF.type, SH.PropertyShape))
            graph.add((prop_shape, SH.path, path))
            graph.add((prop_shape, SH.datatype, xsd_datatype(prop.data_type)))
            if prop.required:
                graph.add((prop_shape, SH.minCount, Literal(1)))
    return graph


def build_shapes(ontology: Ontology) -> str:
    """Generate SHACL NodeShapes as Turtle (one NodeShape per ObjectType)."""
    return build_shapes_graph(ontology).serialize(format="turtle")


def validate_graph(data_graph: str, ontology: Ontology) -> list[str]:
    """Validate a Turtle instance data graph against the ontology's shapes.

    Returns a list of human-readable violation messages; an empty list means
    the data graph conforms.
    """
    data = Graph()
    data.parse(data=data_graph, format="turtle")
    shapes = build_shapes_graph(ontology)
    conforms, results_graph, _results_text = validate(data, shacl_graph=shapes, inference="none")
    if conforms or results_graph is None:
        return []

    messages: list[str] = []
    for result in results_graph.subjects(RDF.type, SH.ValidationResult):
        focus = results_graph.value(result, SH.focusNode)
        # pyshacl emits sh:resultPath/sh:resultMessage (SHACL 1.0 Core terms);
        # fall back to sh:path/sh:message for SHACL-AF style result graphs.
        path = (
            results_graph.value(result, SH.resultPath)
            or results_graph.value(result, SH.path)
        )
        message = (
            results_graph.value(result, SH.resultMessage)
            or results_graph.value(result, SH.message)
        )
        parts = [str(part) for part in (focus, path, message) if part is not None]
        messages.append(" | ".join(parts))
    return messages
