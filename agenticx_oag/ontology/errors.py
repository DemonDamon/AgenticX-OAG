"""Exceptions for the ontology core model."""


class OntologyError(Exception):
    """Base class for all ontology-related errors."""


class OntologyValidationError(OntologyError):
    """Raised when an ontology violates naming, reference-integrity or type constraints.

    Intentionally not a ``ValueError`` subclass so that pydantic ``field_validator``
    propagates it verbatim instead of wrapping it into a pydantic ValidationError.
    """
