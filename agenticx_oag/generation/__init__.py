"""OAG generation: pack-constrained generator + citation validator (P05)."""

from agenticx_oag.generation.oag import (
    CITATION_RE,
    Citation,
    OAGAnswer,
    OAGGenerator,
    parse_citations,
)
from agenticx_oag.generation.validate import (
    LEAD_WHITELIST,
    CitationValidator,
    CitationViolation,
    iter_sentences,
)

__all__ = [
    "CITATION_RE",
    "LEAD_WHITELIST",
    "Citation",
    "CitationValidator",
    "CitationViolation",
    "OAGAnswer",
    "OAGGenerator",
    "iter_sentences",
    "parse_citations",
]
