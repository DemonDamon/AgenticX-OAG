"""FR-6 tests: OWL (TBox) Turtle/JSON-LD export."""

from __future__ import annotations

from rdflib import OWL, RDF, RDFS, Graph, URIRef
from rdflib.namespace import XSD

from agenticx_oag.ontology import Ontology, to_jsonld, to_turtle
from agenticx_oag.ontology.owl_export import (
    base_iri,
    class_iri,
    link_iri,
    property_iri,
)


def test_turtle_parseable(bank_aml_ontology: Ontology) -> None:
    turtle = to_turtle(bank_aml_ontology)
    graph = Graph()
    graph.parse(data=turtle, format="turtle")
    assert len(bank_aml_ontology.object_types) == 8
    assert len(graph) >= len(bank_aml_ontology.object_types) * 3


def test_tbox_structure(bank_aml_ontology: Ontology) -> None:
    graph = Graph().parse(data=to_turtle(bank_aml_ontology), format="turtle")

    classes = set(graph.subjects(RDF.type, OWL.Class))
    assert classes == {class_iri(bank_aml_ontology, ot.api_name) for ot in bank_aml_ontology.object_types}

    object_properties = set(graph.subjects(RDF.type, OWL.ObjectProperty))
    assert object_properties == {link_iri(bank_aml_ontology, lt.api_name) for lt in bank_aml_ontology.link_types}

    datatype_properties = set(graph.subjects(RDF.type, OWL.DatatypeProperty))
    expected = {
        property_iri(bank_aml_ontology, ot.api_name, prop.api_name)
        for ot in bank_aml_ontology.object_types
        for prop in ot.properties
    }
    assert datatype_properties == expected
    # every datatype property declares domain and range
    for prop in datatype_properties:
        assert graph.value(prop, RDFS.domain) is not None
        assert graph.value(prop, RDFS.range) is not None


def test_datatype_property_domain_and_range(bank_aml_ontology: Ontology) -> None:
    graph = Graph().parse(data=to_turtle(bank_aml_ontology), format="turtle")
    risk_level = property_iri(bank_aml_ontology, "Customer", "riskLevel")
    assert graph.value(risk_level, RDFS.domain) == class_iri(bank_aml_ontology, "Customer")
    assert graph.value(risk_level, RDFS.range) == XSD.string

    balance = property_iri(bank_aml_ontology, "Account", "balance")
    assert graph.value(balance, RDFS.range) == XSD.double

    hit_date = property_iri(bank_aml_ontology, "SanctionHit", "hitDate")
    assert graph.value(hit_date, RDFS.range) == XSD.dateTime


def test_object_property_domain_and_range(bank_aml_ontology: Ontology) -> None:
    graph = Graph().parse(data=to_turtle(bank_aml_ontology), format="turtle")
    owns = link_iri(bank_aml_ontology, "owns")
    assert graph.value(owns, RDFS.domain) == class_iri(bank_aml_ontology, "Customer")
    assert graph.value(owns, RDFS.range) == class_iri(bank_aml_ontology, "Account")


def test_parent_exported_as_subclass_of(sample_ontology: Ontology) -> None:
    graph = Graph().parse(data=to_turtle(sample_ontology), format="turtle")
    assert (
        class_iri(sample_ontology, "Customer"),
        RDFS.subClassOf,
        class_iri(sample_ontology, "Party"),
    ) in graph
    assert (
        class_iri(sample_ontology, "Account"),
        RDFS.subClassOf,
        class_iri(sample_ontology, "Party"),
    ) in graph


def test_jsonld_parseable(bank_aml_ontology: Ontology) -> None:
    jsonld = to_jsonld(bank_aml_ontology)
    graph = Graph()
    graph.parse(data=jsonld, format="json-ld")
    assert len(graph) > 0

    turtle_graph = Graph().parse(data=to_turtle(bank_aml_ontology), format="turtle")
    assert len(graph) == len(turtle_graph)


def test_labels_preserved(bank_aml_ontology: Ontology) -> None:
    graph = Graph().parse(data=to_turtle(bank_aml_ontology), format="turtle")
    customer = class_iri(bank_aml_ontology, "Customer")
    labels = {str(label) for label in graph.objects(customer, RDFS.label)}
    assert "客户" in labels


def test_base_iri_is_namespaced(bank_aml_ontology: Ontology) -> None:
    assert base_iri(bank_aml_ontology).endswith("finance.aml#")
    assert isinstance(class_iri(bank_aml_ontology, "Customer"), URIRef)
