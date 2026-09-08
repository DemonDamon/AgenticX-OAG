"""OWL export (TBox only) built on rdflib — part of the ``[owl]`` extra (FR-6).

Only the concept layer is exported:
- ``ObjectType``            -> ``owl:Class`` (``parent`` becomes ``rdfs:subClassOf``)
- ``ObjectType`` properties -> ``owl:DatatypeProperty`` with ``rdfs:domain``/``rdfs:range``
- ``LinkType``              -> ``owl:ObjectProperty``

Link-type properties and instance data are intentionally *not* exported: per the
architecture decision (plan P03), instance-level modeling lives in the graph
store — the OWL export is the outbound RDF interface for the Semantic quadrant
only. This module (and :mod:`agenticx_oag.ontology.shacl`) is the only place
rdflib is required; the core install stays dependency-free (NFR-2).
"""

from __future__ import annotations

from rdflib import RDF, RDFS, OWL, XSD, Graph, Literal, URIRef

from agenticx_oag.ontology.model import DataType, Ontology

#: Placeholder identity for exported TBox documents; scoped per ontology namespace.
BASE_IRI_TEMPLATE = "https://oag.example.org/ontology/{namespace}#"

_XSD_DATATYPES: dict[DataType, URIRef] = {
    DataType.STRING: XSD.string,
    DataType.DOUBLE: XSD.double,
    DataType.INT64: XSD.long,
    DataType.BOOL: XSD.boolean,
    DataType.TIMESTAMP: XSD.dateTime,
    # JSON payloads are string-encoded; there is no direct XSD equivalent.
    DataType.JSON: XSD.string,
}


def base_iri(ontology: Ontology) -> str:
    """Return the base IRI all exported node IRIs are minted under."""
    return BASE_IRI_TEMPLATE.format(namespace=ontology.namespace)


def class_iri(ontology: Ontology, api_name: str) -> URIRef:
    """IRI of an exported owl:Class for an ObjectType api_name."""
    return URIRef(f"{base_iri(ontology)}{api_name}")


def property_iri(ontology: Ontology, owner_api_name: str, property_api_name: str) -> URIRef:
    """IRI of an exported owl:DatatypeProperty (scoped by its owning ObjectType)."""
    return URIRef(f"{base_iri(ontology)}{owner_api_name}.{property_api_name}")


def link_iri(ontology: Ontology, api_name: str) -> URIRef:
    """IRI of an exported owl:ObjectProperty for a LinkType api_name."""
    return URIRef(f"{base_iri(ontology)}{api_name}")


def xsd_datatype(data_type: DataType) -> URIRef:
    """Map a DataType to its XSD range URI."""
    return _XSD_DATATYPES[data_type]


def build_graph(ontology: Ontology) -> Graph:
    """Build the TBox RDF graph for an ontology."""
    graph = Graph()
    graph.bind("oag", base_iri(ontology))

    for obj in ontology.object_types:
        cls = class_iri(ontology, obj.api_name)
        graph.add((cls, RDF.type, OWL.Class))
        graph.add((cls, RDFS.label, Literal(obj.display_name)))
        if obj.description:
            graph.add((cls, RDFS.comment, Literal(obj.description)))
        if obj.parent:
            graph.add((cls, RDFS.subClassOf, class_iri(ontology, obj.parent)))
        for prop in obj.properties:
            node = property_iri(ontology, obj.api_name, prop.api_name)
            graph.add((node, RDF.type, OWL.DatatypeProperty))
            graph.add((node, RDFS.domain, cls))
            graph.add((node, RDFS.range, xsd_datatype(prop.data_type)))
            graph.add((node, RDFS.label, Literal(prop.display_name)))
            if prop.description:
                graph.add((node, RDFS.comment, Literal(prop.description)))

    for link in ontology.link_types:
        node = link_iri(ontology, link.api_name)
        graph.add((node, RDF.type, OWL.ObjectProperty))
        graph.add((node, RDFS.domain, class_iri(ontology, link.source_type)))
        graph.add((node, RDFS.range, class_iri(ontology, link.target_type)))
        graph.add((node, RDFS.label, Literal(link.display_name)))

    return graph


def to_turtle(ontology: Ontology) -> str:
    """Serialize the TBox to Turtle (FR-6)."""
    return build_graph(ontology).serialize(format="turtle")


def to_jsonld(ontology: Ontology) -> str:
    """Serialize the TBox to JSON-LD."""
    return build_graph(ontology).serialize(format="json-ld")
