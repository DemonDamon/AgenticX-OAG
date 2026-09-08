"""FR-1 AC: record model construction and serialization round-trip."""

from agenticx_oag.graph.records import LinkRecord, ObjectRecord, ProvInfo


def test_provinfo_defaults() -> None:
    prov = ProvInfo()
    assert prov.source_doc == ""
    assert prov.span == ""
    assert prov.extracted_at == ""
    assert prov.confidence == 0.0
    assert prov.merged_via == ""
    assert prov.merged_provs == []


def test_object_record_roundtrip() -> None:
    record = ObjectRecord(
        object_type="Customer",
        id="C-001",
        properties={"name": "张三", "riskLevel": "high"},
        prov=ProvInfo(
            source_doc="aml.md",
            span="客户张三……",
            extracted_at="2026-09-08T00:00:00+00:00",
            confidence=0.95,
        ),
    )
    assert ObjectRecord.from_dict(record.to_dict()) == record


def test_link_record_roundtrip() -> None:
    record = LinkRecord(
        link_type="hitsSanction",
        source_id="C-001",
        target_id="S-001",
        properties={"weight": 0.8},
        prov=ProvInfo(source_doc="aml.md", confidence=0.85),
    )
    assert LinkRecord.from_dict(record.to_dict()) == record


def test_prov_merge_chaining() -> None:
    survivor = ObjectRecord(object_type="Customer", id="C-001")
    merged = ObjectRecord(
        object_type="Customer",
        id="C-002",
        prov=ProvInfo(source_doc="b.md", confidence=0.9),
    )
    survivor.properties = {**survivor.properties, **merged.properties}
    survivor.prov.merged_provs.append(merged.prov.model_dump())
    assert survivor.prov.merged_provs == [merged.prov.model_dump()]
