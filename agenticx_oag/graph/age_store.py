"""Apache AGE (PG16) backend for the P02 ``GraphStore`` contract (FR-2).

One AGE graph per ontology namespace (``oag_<namespace with . -> _>``).
Nodes carry the ObjectType api_name as label plus system properties
``__prov`` (provenance JSON string) and ``__ns`` (namespace).

Injection safety: the only f-string interpolations into Cypher are the node
label, the relationship type, the graph name and the hop bound — each is
whitelisted against the ontology (when provided) and ``^[A-Za-z0-9_]+$``.
Property keys *and* values travel inside the ``$rows`` parameter map, so
they never touch the Cypher text.

Verified AGE 1.6 quirks this module works around:
- ``SET n += <expr>`` only accepts a map *variable*, not ``row.props``;
  hence rows are flattened to the full property map and ``SET n += row``.
- AGE's UNWIND expands to an unqualified ``age_unnest`` call, so the
  connection must ``SET search_path`` to include ``ag_catalog``.
- asyncpg has no agtype codec: a text codec is registered and the agtype
  text output (JSON with ``::vertex``/``::edge`` suffixes) is parsed here.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import asyncpg

from agenticx_oag.ontology.model import LinkType, Ontology

_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")
_AGTYPE_SUFFIXES = ("vertex", "edge", "path", "agtype")


def _strip_agtype_suffixes(text: str) -> str:
    """Drop ``::vertex``/``::edge``/``::path``/``::agtype`` tokens outside strings.

    AGE decorates composite values with type suffixes both at the end of a
    whole value (``{...}::vertex``) and on every element of a list
    (``[{...}::vertex, {...}::vertex]``, as returned by ``nodes(p)``). The
    scan is JSON-string aware so a property value that merely contains a
    ``::vertex`` substring survives untouched.
    """
    out: list[str] = []
    in_string = False
    escaped = False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == ":" and text.startswith("::", i):
            for suffix in _AGTYPE_SUFFIXES:
                end = i + 2 + len(suffix)
                if text.startswith(f"::{suffix}", i) and (
                    end == n or not (text[end].isalnum() or text[end] == "_")
                ):
                    i = end  # drop the type token
                    break
            else:
                out.append(ch)
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_agtype(text: str | None) -> Any:
    """Parse AGE's agtype text output (JSON with ``::vertex``/``::edge`` tags)."""
    if text is None:
        return None
    value = _strip_agtype_suffixes(text.strip())
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _vertex_to_record(vertex: dict[str, Any]) -> dict[str, Any]:
    """Convert an AGE vertex dict to the store's object dict shape."""
    props: dict[str, Any] = vertex.get("properties") or {}
    prov_raw = props.pop("__prov", None)
    props.pop("__ns", None)
    if isinstance(prov_raw, str):
        try:
            prov = json.loads(prov_raw)
        except json.JSONDecodeError:
            prov = {}
    elif isinstance(prov_raw, dict):
        prov = prov_raw
    else:
        prov = {}
    return {
        "object_type": vertex.get("label", ""),
        "id": props.get("id", ""),
        "properties": props,
        "prov": prov,
    }


def _edge_to_record(edge: dict[str, Any], source_id: str, target_id: str) -> dict[str, Any]:
    """Convert an AGE edge dict to the store's link dict shape."""
    props: dict[str, Any] = edge.get("properties") or {}
    prov_raw = props.pop("__prov", None)
    if isinstance(prov_raw, str):
        try:
            prov = json.loads(prov_raw)
        except json.JSONDecodeError:
            prov = {}
    elif isinstance(prov_raw, dict):
        prov = prov_raw
    else:
        prov = {}
    return {
        "link_type": edge.get("label", ""),
        "source_id": source_id,
        "target_id": target_id,
        "properties": props,
        "prov": prov,
    }


class AGEGraphStore:
    """``GraphStore`` implementation on PostgreSQL + Apache AGE."""

    def __init__(
        self,
        dsn: str,
        namespace: str,
        ontology: Ontology | None = None,
    ) -> None:
        self._dsn = dsn
        self._namespace = namespace
        self._graph = "oag_" + namespace.replace(".", "_")
        if not _IDENT_RE.match(self._graph):
            raise ValueError(
                f"derived graph name {self._graph!r} must match {_IDENT_RE.pattern}"
            )
        self._ontology = ontology
        self._object_types: set[str] | None = None
        self._link_types: dict[str, LinkType] | None = None
        if ontology is not None:
            self._object_types = {ot.api_name for ot in ontology.object_types}
            self._link_types = {lt.api_name: lt for lt in ontology.link_types}
        self._conn: asyncpg.Connection | None = None
        self._lock = asyncio.Lock()

    @property
    def graph_name(self) -> str:
        return self._graph

    # -- validation (injection line of defense, plan-mandated) ----------------

    def _validate_object_type(self, object_type: str) -> str:
        if not isinstance(object_type, str) or not _IDENT_RE.match(object_type):
            raise ValueError(
                f"invalid object type {object_type!r}: must match {_IDENT_RE.pattern}"
            )
        if self._object_types is not None and object_type not in self._object_types:
            raise ValueError(f"object type {object_type!r} is not defined in the ontology")
        return object_type

    def _validate_link_type(self, link_type: str) -> str:
        if not isinstance(link_type, str) or not _IDENT_RE.match(link_type):
            raise ValueError(
                f"invalid link type {link_type!r}: must match {_IDENT_RE.pattern}"
            )
        if self._link_types is not None and link_type not in self._link_types:
            raise ValueError(f"link type {link_type!r} is not defined in the ontology")
        return link_type

    # -- connection lifecycle ---------------------------------------------------

    async def _ensure(self) -> asyncpg.Connection:
        if self._conn is None:
            conn = await asyncpg.connect(self._dsn)
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS age")
                # AGE's UNWIND expands to an unqualified age_unnest() call.
                await conn.execute("""SET search_path = ag_catalog, "$user", public""")
                await conn.set_type_codec(
                    "agtype",
                    schema="ag_catalog",
                    encoder=str,
                    decoder=str,
                    format="text",
                )
                row = await conn.fetchrow(
                    "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1", self._graph
                )
                if row is None or row[0] == 0:
                    # create_graph raises on an existing graph; guard via catalog.
                    await conn.execute(f"SELECT ag_catalog.create_graph('{self._graph}')")
            except BaseException:
                await conn.close()
                raise
            self._conn = conn
        return self._conn

    async def close(self) -> None:
        async with self._lock:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None

    async def _fetch(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Run one openCypher statement through the ag_catalog.cypher wrapper.

        The statement must RETURN exactly one expression (aliased ``result``).
        """
        conn = await self._ensure()
        sql = f"SELECT * FROM ag_catalog.cypher('{self._graph}', $$ {cypher} $$"
        if params is None:
            sql += ") AS (result agtype)"
            return await conn.fetch(sql)
        sql += ", $1) AS (result agtype)"
        return await conn.fetch(sql, json.dumps(params, ensure_ascii=False, default=str))

    # -- GraphStore interface ----------------------------------------------------

    async def upsert_objects(self, objects: list[dict[str, Any]]) -> None:
        if not objects:
            return
        by_type: dict[str, list[dict[str, Any]]] = {}
        for obj in objects:
            object_type = self._validate_object_type(obj.get("object_type", ""))
            by_type.setdefault(object_type, []).append(obj)
        async with self._lock:
            for object_type, group in by_type.items():
                rows = [
                    {
                        **(obj.get("properties") or {}),
                        "id": obj.get("id", ""),
                        "__prov": json.dumps(
                            obj.get("prov") or {}, ensure_ascii=False, default=str
                        ),
                        "__ns": self._namespace,
                    }
                    for obj in group
                ]
                await self._fetch(
                    f"UNWIND $rows AS row MERGE (n:{object_type} {{id: row.id}}) SET n += row",
                    {"rows": rows},
                )

    async def upsert_links(self, links: list[dict[str, Any]]) -> None:
        if not links:
            return
        by_type: dict[str, list[dict[str, Any]]] = {}
        for link in links:
            link_type = self._validate_link_type(link.get("link_type", ""))
            by_type.setdefault(link_type, []).append(link)
        async with self._lock:
            for link_type, group in by_type.items():
                rows = [
                    {
                        "s": link.get("source_id", ""),
                        "t": link.get("target_id", ""),
                        # the whole SET map travels as one parameter
                        "p": {
                            **(link.get("properties") or {}),
                            "__prov": json.dumps(
                                link.get("prov") or {}, ensure_ascii=False, default=str
                            ),
                        },
                    }
                    for link in group
                ]
                await self._fetch(
                    "UNWIND $rows AS row WITH row.s AS s, row.t AS t, row.p AS p "
                    f"MATCH (a {{id: s}}), (b {{id: t}}) "
                    f"MERGE (a)-[r:{link_type}]->(b) SET r += p",
                    {"rows": rows},
                )

    async def get_objects(
        self, object_type: str, ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        self._validate_object_type(object_type)
        async with self._lock:
            if ids:
                rows = await self._fetch(
                    f"UNWIND $ids AS i MATCH (n:{object_type} {{id: i}}) RETURN n",
                    {"ids": list(ids)},
                )
            else:
                rows = await self._fetch(f"MATCH (n:{object_type}) RETURN n")
        results: list[dict[str, Any]] = []
        for row in rows:
            vertex = parse_agtype(row["result"])
            if isinstance(vertex, dict):
                results.append(_vertex_to_record(vertex))
        return results

    async def neighbors(
        self, object_id: str, link_type: str | None = None, max_hops: int = 2
    ) -> list[dict[str, Any]]:
        if not isinstance(max_hops, int) or max_hops < 1:
            raise ValueError(f"max_hops must be a positive int, got {max_hops!r}")
        rel = ""
        if link_type is not None:
            rel = f":{self._validate_link_type(link_type)}"
        query = (
            f"MATCH p=(n {{id: $id}})-[r{rel}*1..{max_hops}]-(m) "
            "RETURN nodes(p) AS ns, relationships(p) AS rs"
        )
        async with self._lock:
            conn = await self._ensure()
            sql = (
                f"SELECT * FROM ag_catalog.cypher('{self._graph}', $$ {query} $$, $1) "
                "AS (ns agtype, rs agtype)"
            )
            rows = await conn.fetch(sql, json.dumps({"id": object_id}, default=str))
        hops: list[dict[str, Any]] = []
        for row in rows:
            nodes = parse_agtype(row["ns"])
            rels = parse_agtype(row["rs"])
            if not isinstance(nodes, list) or not isinstance(rels, list):
                continue
            if len(nodes) != len(rels) + 1:
                continue
            for depth, edge in enumerate(rels, start=1):
                if not isinstance(edge, dict):
                    continue
                prev_vertex, cur_vertex = nodes[depth - 1], nodes[depth]
                if not isinstance(prev_vertex, dict) or not isinstance(cur_vertex, dict):
                    continue
                prev_gid = prev_vertex.get("id")
                prev_bid = (prev_vertex.get("properties") or {}).get("id", "")
                cur_bid = (cur_vertex.get("properties") or {}).get("id", "")
                if edge.get("start_id") == prev_gid:
                    source_id, target_id = prev_bid, cur_bid
                else:
                    source_id, target_id = cur_bid, prev_bid
                hops.append(
                    {
                        "node": _vertex_to_record(cur_vertex),
                        "rel": _edge_to_record(edge, source_id, target_id),
                        "depth": depth,
                    }
                )
        return hops

    async def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[Any]:
        async with self._lock:
            rows = await self._fetch(cypher, params)
        return [parse_agtype(row["result"]) for row in rows]
