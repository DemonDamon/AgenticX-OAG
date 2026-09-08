"""Unit tests for the agtype text parser used by AGEGraphStore.

Runs without a database: the inputs below are literal AGE text outputs
observed against apache/age:release_PG16_1.6.0.
"""

from __future__ import annotations

from agenticx_oag.graph.age_store import parse_agtype


def test_scalar_without_suffix() -> None:
    assert parse_agtype('"张三"') == "张三"
    assert parse_agtype("1") == 1


def test_vertex_with_end_suffix() -> None:
    raw = '{"id": 1, "label": "Customer", "properties": {"id": "C-001"}}::vertex'
    assert parse_agtype(raw) == {
        "id": 1,
        "label": "Customer",
        "properties": {"id": "C-001"},
    }


def test_path_suffix_stripped() -> None:
    raw = '[{"id": 1}::vertex, {"id": 2}::vertex, {"id": 3}::edge]::path'
    assert parse_agtype(raw) == [{"id": 1}, {"id": 2}, {"id": 3}]


def test_list_with_element_suffixes() -> None:
    # nodes(p) / relationships(p) decorate every element, not the list itself
    raw = (
        '[{"id": 1, "label": "Customer", "properties": {"id": "C-001"}}::vertex, '
        '{"id": 2, "label": "Account", "properties": {"id": "A-101"}}::vertex]'
    )
    parsed = parse_agtype(raw)
    assert isinstance(parsed, list)
    assert [v["properties"]["id"] for v in parsed] == ["C-001", "A-101"]

    raw_edge = (
        '[{"id": 3, "label": "owns", "start_id": 1, "end_id": 2, '
        '"properties": {"__prov": "{\\"confidence\\": 0.8}"}}::edge]'
    )
    edge = parse_agtype(raw_edge)
    assert isinstance(edge, list)
    assert edge[0]["label"] == "owns"
    # the embedded __prov JSON string is preserved verbatim
    assert edge[0]["properties"]["__prov"] == '{"confidence": 0.8}'


def test_suffix_like_text_inside_strings_is_kept() -> None:
    raw = '{"note": "looks like }::vertex inside a string", "n": 5}'
    assert parse_agtype(raw) == {
        "note": "looks like }::vertex inside a string",
        "n": 5,
    }
    assert parse_agtype('"plain ::vertex string"') == "plain ::vertex string"


def test_longer_token_not_confused_with_suffix() -> None:
    # ::vertices must not be treated as a ::vertex suffix
    assert parse_agtype('{"k": "v"} ::vertices') == '{"k": "v"} ::vertices'


def test_none_passthrough_and_garbage_returned_as_text() -> None:
    assert parse_agtype(None) is None
    assert parse_agtype("not json at all") == "not json at all"
