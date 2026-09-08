"""FR-7 tests: SHACL shape generation and instance-graph validation."""

from __future__ import annotations

from rdflib import RDF, Graph
from rdflib.namespace import SH, XSD

from agenticx_oag.ontology import Ontology, build_shapes, validate_graph
from agenticx_oag.ontology.owl_export import base_iri, property_iri


def _customer_data(base: str, *, complete: bool) -> str:
    """A Customer instance with (complete=True) or without required properties."""
    props = [
        ('Customer.id', '"CUST-01"'),
        ('Customer.name', '"深圳华鑫贸易有限公司"'),
        ('Customer.industry', '"大宗商品贸易"'),
        ('Customer.riskLevel', '"高"'),
        ('Customer.region', '"深圳"'),
        ('Customer.estYear', '"2019"^^xsd:double'),
    ]
    if not complete:
        props = [props[0], props[4]]  # keep id + region only; drop the rest
    body = " ;\n    ".join(f"oag:{name} {value}" for name, value in props)
    return f"""
@prefix oag: <{base}> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

oag:CUST-01 a oag:Customer ;
    {body} .
"""


def test_build_shapes_structure(bank_aml_ontology: Ontology) -> None:
    graph = Graph().parse(data=build_shapes(bank_aml_ontology), format="turtle")
    node_shapes = set(graph.subjects(RDF.type, SH.NodeShape))
    assert len(node_shapes) == len(bank_aml_ontology.object_types) == 8

    customer_shape = None
    for shape in node_shapes:
        if "Customer" in str(shape):
            customer_shape = shape
    assert customer_shape is not None

    property_shapes = list(graph.objects(customer_shape, SH.property))
    assert len(property_shapes) == len(bank_aml_ontology.object_types[0].properties)
    for prop_shape in property_shapes:
        assert graph.value(prop_shape, SH.path) is not None
        assert graph.value(prop_shape, SH.datatype) is not None
        min_count = graph.value(prop_shape, SH.minCount)
        if min_count is not None:
            assert int(min_count) == 1  # required -> sh:minCount 1


def test_build_shapes_datatypes(bank_aml_ontology: Ontology) -> None:
    graph = Graph().parse(data=build_shapes(bank_aml_ontology), format="turtle")
    risk_level = property_iri(bank_aml_ontology, "Customer", "riskLevel")
    for shape in graph.subjects(SH.path, risk_level):
        assert graph.value(shape, SH.datatype) == XSD.string

    est_year = property_iri(bank_aml_ontology, "Customer", "estYear")
    for shape in graph.subjects(SH.path, est_year):
        assert graph.value(shape, SH.datatype) == XSD.double


def test_validate_instances_missing_required(bank_aml_ontology: Ontology) -> None:
    base = base_iri(bank_aml_ontology)
    violations = validate_graph(_customer_data(base, complete=False), bank_aml_ontology)
    assert violations, "expected SHACL violations for missing required properties"
    joined = "\n".join(violations)
    # the violation message must name the missing property (path contains it)
    assert "Customer.name" in joined
    assert "Customer.riskLevel" in joined


def test_validate_instances_valid(bank_aml_ontology: Ontology) -> None:
    base = base_iri(bank_aml_ontology)
    assert validate_graph(_customer_data(base, complete=True), bank_aml_ontology) == []


def test_validate_instances_wrong_datatype(bank_aml_ontology: Ontology) -> None:
    base = base_iri(bank_aml_ontology)
    data = _customer_data(base, complete=True).replace(
        '"2019"^^xsd:double', '"not-a-number"'
    )
    violations = validate_graph(data, bank_aml_ontology)
    assert violations
    assert any("estYear" in violation for violation in violations)


def test_validate_graph_empty_data(bank_aml_ontology: Ontology) -> None:
    assert validate_graph("", bank_aml_ontology) == []
