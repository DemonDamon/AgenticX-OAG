"""Pydantic v2 mirror of the P02 ontology contract.

Field names align one-to-one with ``proto/agenticx_oag/ontology/v1/ontology.proto``;
YAML documents use the plain enum literals (``STRING``/``DOUBLE``/... and
``ONE_TO_ONE``/``ONE_TO_MANY``/``MANY_TO_MANY``) which correspond directly to the
proto enum value names.

Naming rules (FR-2):
- ``ObjectType.api_name``: PascalCase (``^[A-Z][A-Za-z0-9]*$``)
- ``PropertyType`` / ``LinkType`` / ``ActionType.api_name``: camelCase (``^[a-z][A-Za-z0-9_]*$``)
- violations raise :class:`~agenticx_oag.ontology.errors.OntologyValidationError`
  at model construction time.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from agenticx_oag.ontology.errors import OntologyValidationError

_OBJECT_TYPE_NAME_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_MEMBER_NAME_PATTERN = re.compile(r"^[a-z][A-Za-z0-9_]*$")
_PRECONDITION_PATTERN = re.compile(r"^[a-z0-9_.:-]+$")


class DataType(str, Enum):
    """Property value type; literals mirror the proto ``DataType`` value names."""

    STRING = "STRING"
    DOUBLE = "DOUBLE"
    INT64 = "INT64"
    BOOL = "BOOL"
    TIMESTAMP = "TIMESTAMP"
    JSON = "JSON"


class Cardinality(str, Enum):
    """Link multiplicity; literals mirror the proto ``Cardinality`` value names."""

    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_MANY = "MANY_TO_MANY"


def _require_object_type_name(cls: type[BaseModel], value: str) -> str:
    if not _OBJECT_TYPE_NAME_PATTERN.match(value):
        raise OntologyValidationError(
            f"{cls.__name__}.api_name {value!r} must match "
            f"'{_OBJECT_TYPE_NAME_PATTERN.pattern}' (PascalCase)"
        )
    return value


def _require_member_name(cls: type[BaseModel], value: str) -> str:
    if not _MEMBER_NAME_PATTERN.match(value):
        raise OntologyValidationError(
            f"{cls.__name__}.api_name {value!r} must match "
            f"'{_MEMBER_NAME_PATTERN.pattern}' (camelCase)"
        )
    return value


class PropertyType(BaseModel):
    """A typed attribute of an object type or link type (proto message PropertyType)."""

    api_name: str
    display_name: str
    data_type: DataType = DataType.STRING
    required: bool = False
    description: str = ""
    enum_values: list[str] = Field(default_factory=list)

    @field_validator("api_name")
    @classmethod
    def _validate_api_name(cls, value: str) -> str:
        return _require_member_name(cls, value)


class ObjectType(BaseModel):
    """An entity class in the ontology (proto message ObjectType)."""

    api_name: str
    display_name: str
    properties: list[PropertyType] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)
    parent: str = ""
    description: str = ""

    @field_validator("api_name")
    @classmethod
    def _validate_api_name(cls, value: str) -> str:
        return _require_object_type_name(cls, value)


class LinkType(BaseModel):
    """A typed relation between two object types (proto message LinkType)."""

    api_name: str
    display_name: str
    source_type: str
    target_type: str
    cardinality: Cardinality = Cardinality.MANY_TO_MANY
    properties: list[PropertyType] = Field(default_factory=list)

    @field_validator("api_name")
    @classmethod
    def _validate_api_name(cls, value: str) -> str:
        return _require_member_name(cls, value)


class ActionType(BaseModel):
    """A governed write action on the ontology (proto message ActionType)."""

    api_name: str
    display_name: str
    target_types: list[str] = Field(default_factory=list)
    parameters: list[PropertyType] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    approval_policy: str = "none"  # "none" | "single" | "two_level"
    rollback_handler: str = ""

    @field_validator("api_name")
    @classmethod
    def _validate_api_name(cls, value: str) -> str:
        return _require_member_name(cls, value)


class Ontology(BaseModel):
    """The root ontology document (proto message Ontology)."""

    namespace: str = Field(..., pattern=r"^[a-z][a-z0-9_.]*$")
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    object_types: list[ObjectType]
    link_types: list[LinkType] = Field(default_factory=list)
    action_types: list[ActionType] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    def validate(self) -> None:
        """Validate reference integrity (FR-3) and type constraints (FR-4).

        All problems are aggregated into a single
        :class:`~agenticx_oag.ontology.errors.OntologyValidationError`.
        """
        problems: list[str] = []

        object_types: dict[str, ObjectType] = {}
        for obj in self.object_types:
            if obj.api_name in object_types:
                problems.append(f"duplicate ObjectType api_name {obj.api_name!r}")
            else:
                object_types[obj.api_name] = obj

        link_names: set[str] = set()
        for link in self.link_types:
            if link.api_name in link_names:
                problems.append(f"duplicate LinkType api_name {link.api_name!r}")
            link_names.add(link.api_name)

        action_names: set[str] = set()
        for action in self.action_types:
            if action.api_name in action_names:
                problems.append(f"duplicate ActionType api_name {action.api_name!r}")
            action_names.add(action.api_name)

        # Link types must point at existing object types.
        for link in self.link_types:
            if link.source_type not in object_types:
                problems.append(
                    f"LinkType {link.api_name!r}: source_type {link.source_type!r} "
                    "is not a known ObjectType"
                )
            if link.target_type not in object_types:
                problems.append(
                    f"LinkType {link.api_name!r}: target_type {link.target_type!r} "
                    "is not a known ObjectType"
                )
            _check_properties(f"LinkType {link.api_name!r}", link.properties, problems)

        # Object type internals: property constraints and primary key references.
        for obj in self.object_types:
            properties = _check_properties(
                f"ObjectType {obj.api_name!r}", obj.properties, problems
            )
            for key in obj.primary_key:
                prop = properties.get(key)
                if prop is None:
                    problems.append(
                        f"ObjectType {obj.api_name!r}: primary_key {key!r} does not "
                        "reference an existing property"
                    )
                elif not prop.required:
                    problems.append(
                        f"ObjectType {obj.api_name!r}: primary_key {key!r} must reference "
                        "a required property"
                    )
                elif prop.data_type in (DataType.TIMESTAMP, DataType.JSON):
                    problems.append(
                        f"ObjectType {obj.api_name!r}: primary_key {key!r} cannot use "
                        f"data_type {prop.data_type.value}"
                    )
            if obj.parent and obj.parent not in object_types:
                problems.append(
                    f"ObjectType {obj.api_name!r}: parent {obj.parent!r} is not a known ObjectType"
                )

        # Parent chains must be acyclic.
        for obj in self.object_types:
            seen = {obj.api_name}
            chain = [obj.api_name]
            current: str | None = obj.parent or None
            while current is not None:
                if current in seen:
                    problems.append(
                        f"ObjectType parent cycle detected: {' -> '.join(chain)} -> {current}"
                    )
                    break
                seen.add(current)
                chain.append(current)
                parent_obj = object_types.get(current)
                current = parent_obj.parent or None if parent_obj is not None else None

        # Action types: target references and precondition id format.
        for action in self.action_types:
            for target in action.target_types:
                if target not in object_types:
                    problems.append(
                        f"ActionType {action.api_name!r}: target_type {target!r} "
                        "is not a known ObjectType"
                    )
            for precondition in action.preconditions:
                # Preconditions may forward-reference P08 rule ids; only the format is checked.
                if not _PRECONDITION_PATTERN.match(precondition):
                    problems.append(
                        f"ActionType {action.api_name!r}: precondition {precondition!r} "
                        f"must match {_PRECONDITION_PATTERN.pattern}"
                    )
            _check_properties(f"ActionType {action.api_name!r}", action.parameters, problems)

        if problems:
            raise OntologyValidationError(
                f"Ontology {self.namespace!r} v{self.version} is invalid "
                f"({len(problems)} problem(s)):\n"
                + "\n".join(f"  - {problem}" for problem in problems)
            )


def _check_properties(
    owner: str, properties: list[PropertyType], problems: list[str]
) -> dict[str, PropertyType]:
    """Index properties by api_name; report duplicates and FR-4 violations as problems."""
    index: dict[str, PropertyType] = {}
    for prop in properties:
        if prop.api_name in index:
            problems.append(f"{owner}: duplicate property {prop.api_name!r}")
        else:
            index[prop.api_name] = prop
        if prop.enum_values and prop.data_type is not DataType.STRING:
            problems.append(
                f"{owner}: property {prop.api_name!r} declares enum_values but data_type "
                f"is {prop.data_type.value} (must be STRING)"
            )
    return index
