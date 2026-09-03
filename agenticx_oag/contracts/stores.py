"""Storage and integration provider contracts.

Each Protocol below is a hard contract consumed by later subplans (P03-P06);
do not change signatures without a recorded migration in the plan.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GraphStore(Protocol):
    async def upsert_objects(self, objects: list[dict[str, Any]]) -> None: ...
    async def upsert_links(self, links: list[dict[str, Any]]) -> None: ...
    async def get_objects(self, object_type: str, ids: list[str] | None = None) -> list[dict[str, Any]]: ...
    async def neighbors(self, object_id: str, link_type: str | None = None, max_hops: int = 2) -> list[dict[str, Any]]: ...
    async def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


@runtime_checkable
class VectorStore(Protocol):
    async def upsert(self, collection: str, ids: list[str], vectors: list[list[float]], metas: list[dict[str, Any]]) -> None: ...
    async def search(self, collection: str, vector: list[float], top_k: int, filter: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class LLMProvider(Protocol):
    async def complete(self, prompt: str, *, system: str | None = None, json_mode: bool = False) -> str: ...


@runtime_checkable
class AuditSink(Protocol):
    # 事件结构与 P07 对齐：action_id/from/to/actor/ts/payload_hash
    async def emit(self, event: dict[str, Any]) -> None: ...


@runtime_checkable
class EventBus(Protocol):
    async def publish(self, topic: str, payload: bytes) -> None: ...


@runtime_checkable
class IDPProvider(Protocol):
    # 返回 {subject, roles, tenant_id, ...}
    async def verify_token(self, token: str) -> dict[str, Any]: ...


@runtime_checkable
class ApprovalProvider(Protocol):
    async def request(self, action_id: str, summary: str, approvers: list[str]) -> str: ...  # 返回审批单 ID
    async def status(self, ticket_id: str) -> str: ...  # "pending"|"approved"|"rejected"


@runtime_checkable
class Notifier(Protocol):
    async def send(self, to: str, title: str, body: str) -> None: ...
