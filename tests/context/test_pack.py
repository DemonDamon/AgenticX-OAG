"""FR-3: ContextPack models, JSON roundtrip, claim-ledger schema conformance.

The ledger schema (``additionalProperties: false``, only four top-level keys)
cannot validate a full pack dump, so the ledger snapshot is exposed via
``ContextPack.to_ledger()`` — the nested-projection decision recorded in the
plan report.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from agenticx_oag.context.pack import (
    CLAIM_LEDGER_SCHEMA_VERSION,
    Claim,
    ClaimScope,
    ClaimStatus,
    ContextPack,
    Evidence,
    LedgerEvidence,
    ObjectRef,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schemas" / "claim-ledger.schema.json"


@pytest.fixture(scope="module")
def claim_ledger_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _pack() -> ContextPack:
    ev1 = Evidence(
        id="E1",
        object_id="cust-1",
        text="客户张三持有账户 A",
        score=0.8,
        provenance="https://db.example/cust-1",
    )
    ev2 = Evidence(
        id="E2",
        object_id="txn-1",
        text="账户 A 在 2026-08 发生大额转账",
        score=0.4,
        provenance="graph:cust-1",
    )
    return ContextPack(
        pack_id="pack_abc123def456",
        question="张三名下账户近期有哪些异常？",
        rewrites=["张三名下账户近期有哪些异常？", "客户张三的账户异常交易列表"],
        object_refs=[
            ObjectRef(id="cust-1", object_type="Customer"),
            ObjectRef(id="txn-1", object_type="Transaction"),
        ],
        evidence=[ev1, ev2],
        claims=[
            Claim(
                claim_id="claim:1",
                text="客户张三持有账户 A",
                status=ClaimStatus.SUPPORTED,
                entities=["entity:cust-1"],
                evidence=[LedgerEvidence.from_evidence(ev1, on_date="2026-09-03")],
                evidence_ids=["E1"],
                confidence=0.9,
            ),
            Claim(
                claim_id="claim:2",
                text="账户 A 的转账是否异常尚不能确认",
                status=ClaimStatus.UNVERIFIED,
                entities=["entity:txn-1"],
                relations=["rel:involves"],
                scope=ClaimScope(time_range="2026-08"),
                evidence=[LedgerEvidence.from_evidence(ev2, on_date="2026-09-03")],
                evidence_ids=["E2"],
                confidence=0.3,
                limitations=["证据仅覆盖单一交易"],
            ),
        ],
        uncertainty="账户异常判断缺少风控规则证据。",
        created_at=datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC),
    )


def test_json_roundtrip() -> None:
    pack = _pack()
    restored = ContextPack.from_json(pack.to_json())
    assert restored == pack


def test_pack_id_default_format() -> None:
    pack = ContextPack(question="q")
    assert pack.pack_id.startswith("pack_")
    assert len(pack.pack_id) == len("pack_") + 12


def test_to_ledger_validates_against_claim_ledger_schema(
    claim_ledger_schema: dict,
) -> None:
    ledger = _pack().to_ledger()
    jsonschema.validate(ledger, claim_ledger_schema)
    assert ledger["schema_version"] == CLAIM_LEDGER_SCHEMA_VERSION
    assert ledger["research_question"] == "张三名下账户近期有哪些异常？"
    assert [claim["claim_id"] for claim in ledger["claims"]] == ["claim:1", "claim:2"]
    # Pack 内部关联字段不泄漏进 ledger 投影（schema additionalProperties=false）
    assert all("evidence_ids" not in claim for claim in ledger["claims"])


def test_ledger_evidence_projection(claim_ledger_schema: dict) -> None:
    ledger = _pack().to_ledger()
    jsonschema.validate(ledger, claim_ledger_schema)
    sources = {
        item["source_id"]: item for claim in ledger["claims"] for item in claim["evidence"]
    }
    assert sources["src:E1"]["url"] == "https://db.example/cust-1"
    assert sources["src:E2"]["url"] == "urn:agenticx:evidence:E2"
    assert sources["src:E1"]["strength"] == "high"  # 0.8 >= 2/3
    assert sources["src:E2"]["strength"] == "medium"  # 1/3 <= 0.4 < 2/3
    assert sources["src:E1"]["excerpt"] == "客户张三持有账户 A"


def test_schema_enforcement_is_real(claim_ledger_schema: dict) -> None:
    ledger = _pack().to_ledger()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**ledger, "schema_version": "9.9.9"}, claim_ledger_schema)


def test_claim_status_matches_schema_enum(claim_ledger_schema: dict) -> None:
    schema_values = set(
        claim_ledger_schema["$defs"]["claim"]["properties"]["status"]["enum"]
    )
    assert {status.value for status in ClaimStatus} == schema_values


def test_claim_rejects_non_schema_id() -> None:
    with pytest.raises(ValueError):
        Claim(
            claim_id="C1",  # plan 的简写；schema 要求 "claim:" 前缀
            text="x",
            entities=["entity:a"],
            evidence=[LedgerEvidence(source_id="src:E1")],
        )
