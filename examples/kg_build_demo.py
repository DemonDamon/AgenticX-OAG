"""P04 end-to-end demo (FR-7): docs -> ontology-guided extraction -> AGE.

Runs the full ingest pipeline over examples/docs/aml-*.md against the AML
ontology with a mock LLM (fixed JSON responses keyed by document), then
queries all Customer nodes from the AGE graph and prints them.

Usage:
    TEST_PG_DSN=postgresql://agenticx:agenticx@localhost:5433/agenticx \
        .venv/bin/python examples/kg_build_demo.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from fixtures.mock_llm import MockLLM

from agenticx_oag.graph.age_store import AGEGraphStore
from agenticx_oag.ingest.pipeline import IngestPipeline
from agenticx_oag.ontology.io import load_ontology

DEFAULT_DSN = "postgresql://agenticx:agenticx@localhost:5433/agenticx"
ONTOLOGY_PATH = REPO_ROOT / "templates" / "finance" / "aml" / "ontology.yaml"

# Fixed mock responses per example doc; values use ontology property names.
_RESPONSES_BY_DOC: dict[str, str] = {
    "aml-customer-onboarding.md": json.dumps(
        {
            "objects": [
                {"type": "Customer", "id": "C-001",
                 "properties": {"name": "华信国际贸易有限公司", "industry": "进出口贸易",
                                "riskLevel": "high", "region": "华东", "estYear": 2012},
                 "source_span": "对公客户华信国际贸易有限公司（客户编号 C-001）……", "confidence": 0.95},
                {"type": "Customer", "id": "C-002",
                 "properties": {"name": "张伟", "riskLevel": "medium"},
                 "source_span": "个人客户张伟（C-002）评定为中风险", "confidence": 0.94},
                {"type": "Customer", "id": "C-003",
                 "properties": {"name": "李娜", "riskLevel": "low"},
                 "source_span": "李娜（C-003）为低风险（low）", "confidence": 0.94},
                {"type": "Customer", "id": "C-004",
                 "properties": {"name": "王强", "riskLevel": "medium"},
                 "source_span": "王强（C-004）为中风险（medium）", "confidence": 0.93},
                {"type": "Account", "id": "A-101",
                 "properties": {"name": "华信国际贸易对公账户", "accountType": "对公",
                                "balance": 0.0, "openDate": "2026-03-02"},
                 "source_span": "开立对公账户 A-101", "confidence": 0.9},
                {"type": "Account", "id": "A-102",
                 "properties": {"name": "张伟个人账户", "accountType": "个人",
                                "balance": 0.0, "openDate": "2026-03-05"},
                 "source_span": "开立个人账户 A-102", "confidence": 0.9},
                {"type": "Account", "id": "A-103",
                 "properties": {"name": "李娜个人账户", "accountType": "个人",
                                "balance": 0.0, "openDate": "2026-03-06"},
                 "source_span": "开立个人账户 A-103", "confidence": 0.9},
                {"type": "DueDiligence", "id": "D-501",
                 "properties": {"name": "华信国际贸易增强尽调", "ddLevel": "enhanced",
                                "conclusion": "持续监控", "completedDate": "2026-03-20"},
                 "source_span": "形成尽调报告 D-501，结论为「持续监控」", "confidence": 0.92},
                {"type": "DueDiligence", "id": "D-502",
                 "properties": {"name": "张伟标准尽调", "ddLevel": "standard",
                                "conclusion": "无异常", "completedDate": "2026-03-18"},
                 "source_span": "报告编号 D-502，结论为「无异常」", "confidence": 0.92},
            ],
            "links": [
                {"type": "owns", "source_id": "C-001", "target_id": "A-101",
                 "source_span": "开立对公账户 A-101", "confidence": 0.9},
                {"type": "owns", "source_id": "C-002", "target_id": "A-102",
                 "source_span": "开立个人账户 A-102", "confidence": 0.9},
                {"type": "owns", "source_id": "C-003", "target_id": "A-103",
                 "source_span": "开立个人账户 A-103", "confidence": 0.9},
                {"type": "reviewedBy", "source_id": "C-001", "target_id": "D-501",
                 "source_span": "合规部对华信国际贸易启动增强型尽职调查", "confidence": 0.88},
                {"type": "reviewedBy", "source_id": "C-002", "target_id": "D-502",
                 "source_span": "对张伟完成标准尽调", "confidence": 0.88},
            ],
        },
        ensure_ascii=False,
    ),
    "aml-loan-collateral.md": json.dumps(
        {
            "objects": [
                {"type": "Customer", "id": "C-007",
                 "properties": {"name": "刘洋", "industry": "建材批发", "riskLevel": "medium"},
                 "source_span": "刘洋（客户编号 C-007，建材批发行业，中风险）", "confidence": 0.94},
                {"type": "Customer", "id": "C-008",
                 "properties": {"name": "周芳", "industry": "零售", "riskLevel": "low"},
                 "source_span": "周芳（C-008，零售行业，低风险）", "confidence": 0.94},
                {"type": "Customer", "id": "C-009",
                 "properties": {"name": "吴磊", "industry": "物流", "riskLevel": "medium"},
                 "source_span": "物流企业主吴磊（C-009，中风险）", "confidence": 0.9},
                {"type": "Customer", "id": "C-010",
                 "properties": {"name": "郑爽", "industry": "珠宝", "riskLevel": "high"},
                 "source_span": "郑爽（C-010，珠宝行业，高风险）", "confidence": 0.94},
                {"type": "LoanApplication", "id": "L-401",
                 "properties": {"name": "刘洋流动资金贷款", "amount": 300.0,
                                "loanType": "流动资金", "status": "审批中",
                                "applyDate": "2026-05-03"},
                 "source_span": "申请流动资金贷款 L-401，金额 300 万元", "confidence": 0.93},
                {"type": "LoanApplication", "id": "L-402",
                 "properties": {"name": "周芳经营贷", "amount": 80.0,
                                "loanType": "经营", "status": "已受理",
                                "applyDate": "2026-05-04"},
                 "source_span": "申请经营贷 L-402，金额 80 万元", "confidence": 0.93},
                {"type": "LoanApplication", "id": "L-403",
                 "properties": {"name": "郑爽抵押贷款", "amount": 550.0,
                                "loanType": "抵押", "status": "暂缓转人工",
                                "applyDate": "2026-05-06"},
                 "source_span": "申请抵押贷款 L-403，金额 550 万元", "confidence": 0.93},
                {"type": "Collateral", "id": "CO-501",
                 "properties": {"name": "刘洋厂房", "collateralType": "厂房",
                                "appraisedValue": 420.0, "location": "华东"},
                 "source_span": "抵押物 CO-501，评估价值 420 万元", "confidence": 0.92},
                {"type": "Collateral", "id": "CO-502",
                 "properties": {"name": "郑爽商铺", "collateralType": "商铺",
                                "appraisedValue": 610.0, "location": "华东"},
                 "source_span": "抵押物 CO-502，评估价值 610 万元", "confidence": 0.92},
            ],
            "links": [
                {"type": "applies", "source_id": "C-007", "target_id": "L-401",
                 "source_span": "刘洋……申请流动资金贷款 L-401", "confidence": 0.9},
                {"type": "applies", "source_id": "C-008", "target_id": "L-402",
                 "source_span": "周芳……申请经营贷 L-402", "confidence": 0.9},
                {"type": "applies", "source_id": "C-010", "target_id": "L-403",
                 "source_span": "郑爽……申请抵押贷款 L-403", "confidence": 0.9},
                {"type": "securedBy", "source_id": "L-401", "target_id": "CO-501",
                 "source_span": "以名下厂房（抵押物 CO-501……）抵押担保", "confidence": 0.88},
                {"type": "securedBy", "source_id": "L-403", "target_id": "CO-502",
                 "source_span": "以商铺（抵押物 CO-502……）作为抵押", "confidence": 0.88},
            ],
        },
        ensure_ascii=False,
    ),
    "aml-suspicious-transactions.md": json.dumps(
        {
            "objects": [
                {"type": "Customer", "id": "C-005",
                 "properties": {"name": "陈刚", "industry": "跨境咨询服务", "riskLevel": "high"},
                 "source_span": "新入名单客户陈刚（C-005，跨境咨询服务行业，高风险）", "confidence": 0.93},
                {"type": "Customer", "id": "C-006",
                 "properties": {"name": "赵敏", "industry": "电子产品贸易", "riskLevel": "medium"},
                 "source_span": "赵敏（C-006，电子产品贸易，中风险）", "confidence": 0.93},
                {"type": "Transaction", "id": "T-201",
                 "properties": {"name": "境外咨询费转账", "amount": 480.0, "direction": "out",
                                "counterparty": "Chen Trading Ltd", "time": "2026-04-12T09:30:00"},
                 "source_span": "T-201 向境外咨询公司转账 480 万元", "confidence": 0.95},
                {"type": "Transaction", "id": "T-202",
                 "properties": {"name": "快进快出转出", "amount": 460.0, "direction": "out",
                                "counterparty": "多家个人账户", "time": "2026-04-12T10:10:00"},
                 "source_span": "T-202 于收款后 40 分钟内将 460 万元转出", "confidence": 0.95},
                {"type": "Transaction", "id": "T-203",
                 "properties": {"name": "张伟账户转款", "amount": 35.0, "direction": "out",
                                "counterparty": "赵敏", "time": "2026-04-12T14:20:00"},
                 "source_span": "发生交易 T-203，金额 35 万元，交易对手为赵敏", "confidence": 0.94},
                {"type": "SanctionHit", "id": "S-301",
                 "properties": {"name": "OFAC SDN 命中", "listType": "OFAC",
                                "matchedEntity": "Chen Trading Ltd", "hitDate": "2026-04-12"},
                 "source_span": "收款方命中 OFAC SDN 制裁名单（命中记录 S-301）", "confidence": 0.9},
                {"type": "SuspiciousTxn", "id": "ST-601",
                 "properties": {"name": "快进快出可疑交易报告", "reason": "快进快出、疑似资金过渡账户",
                                "status": "待复核", "priority": "high",
                                "detected": "2026-04-12T16:00:00"},
                 "source_span": "系统对 T-202 生成可疑交易报告 ST-601", "confidence": 0.9},
            ],
            "links": [
                {"type": "initiates", "source_id": "A-101", "target_id": "T-201",
                 "source_span": "账户 A-101（华信国际贸易）当日发生两笔大额交易", "confidence": 0.9},
                {"type": "initiates", "source_id": "A-101", "target_id": "T-202",
                 "source_span": "T-202 于收款后 40 分钟内将 460 万元转出", "confidence": 0.9},
                {"type": "initiates", "source_id": "A-102", "target_id": "T-203",
                 "source_span": "个人账户 A-102（张伟）发生交易 T-203", "confidence": 0.9},
                {"type": "hitsSanction", "source_id": "T-201", "target_id": "S-301",
                 "source_span": "交易 T-201 的收款方命中 OFAC SDN 制裁名单", "confidence": 0.88},
                {"type": "flaggedAs", "source_id": "T-202", "target_id": "ST-601",
                 "source_span": "系统对 T-202 生成可疑交易报告 ST-601", "confidence": 0.88},
                {"type": "risk", "source_id": "C-005", "target_id": "C-001",
                 "source_span": "陈刚与华信国际贸易存在疑似关联交易关系", "confidence": 0.8},
            ],
        },
        ensure_ascii=False,
    ),
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P04 KG build demo (mock LLM)")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("TEST_PG_DSN") or DEFAULT_DSN,
        help="PostgreSQL DSN with AGE (default: TEST_PG_DSN env or localhost:5433)",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="use a real LLM provider instead of the mock (not implemented in P04)",
    )
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.real:
        print("real LLM provider is out of P04 scope; run without --real", file=sys.stderr)
        return 2

    docs = sorted((REPO_ROOT / "examples" / "docs").glob("aml-*.md"))
    missing = [doc.name for doc in docs if doc.name not in _RESPONSES_BY_DOC]
    if missing:
        print(f"no mock response scripted for: {missing}", file=sys.stderr)
        return 2

    ontology = load_ontology(ONTOLOGY_PATH)
    store = AGEGraphStore(args.dsn, ontology.namespace, ontology=ontology)
    try:
        responses = [_RESPONSES_BY_DOC[doc.name] for doc in docs]
        report = await IngestPipeline().run(docs, ONTOLOGY_PATH, store, MockLLM(responses))
        print(f"[demo] ingest report: {report}")
        print(f"[demo] graph: {store.graph_name}")

        customers: list[dict[str, Any]] = await store.get_objects("Customer")
        print(f"[demo] {len(customers)} Customer nodes:")
        for customer in sorted(customers, key=lambda c: c["id"]):
            props = customer["properties"]
            print(
                f"  - {customer['id']:<8} {props.get('name', '')}"
                f"  riskLevel={props.get('riskLevel', '?')}"
                f"  industry={props.get('industry', '?')}"
            )
    finally:
        await store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
