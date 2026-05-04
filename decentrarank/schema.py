"""
DecentraRank Universal Schema — Python implementation.

This module defines the canonical Entity dataclass and validation logic.
See SCHEMA.md for the full specification.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
import hashlib
import json


# Default reference weights — overridable per-domain via MABS calibration.
DEFAULT_WEIGHTS: Dict[str, float] = {
    "relevance":   0.20,
    "recency":     0.15,
    "provenance":  0.20,
    "reliability": 0.30,
    "cost":        0.15,
}

SCHEMA_VERSION = "0.1.0"


@dataclass
class Entity:
    """
    Canonical ranked entity, domain-agnostic.

    Universal signals (relevance, recency, provenance, reliability, cost) must
    all be populated by the domain adapter; the composite_score is derived.
    """

    entity_type: str
    domain:      str
    producer:    str
    submitted_at: int
    last_updated: int

    relevance:    float = 0.0
    recency:      float = 0.0
    provenance:   float = 0.0
    reliability:  float = 0.0
    cost:         float = 0.0

    extensions: Dict[str, Any] = field(default_factory=dict)

    composite_score: Optional[float] = None
    entity_id:       Optional[str]   = None
    previous_entity_id: Optional[str] = None
    schema_version:  str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        """Validate universal-signal ranges."""
        for name in ("relevance", "recency", "provenance", "reliability", "cost"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"Universal signal '{name}' must be in [0.0, 1.0], got {value}"
                )
        if self.entity_id is None:
            self.entity_id = self.compute_id()

    def compute_id(self) -> str:
        """Compute the content-addressable identifier for this entity."""
        canonical = json.dumps(
            {
                "entity_type":  self.entity_type,
                "domain":       self.domain,
                "producer":     self.producer,
                "submitted_at": self.submitted_at,
                "extensions":   self.extensions,
            },
            sort_keys=True,
        ).encode("utf-8")
        return "0x" + hashlib.sha256(canonical).hexdigest()[:40]

    def score(self, weights: Optional[Dict[str, float]] = None) -> float:
        """
        Compute the composite ranking score.

        Weights default to the reference weights from SCHEMA.md and may be
        overridden per-domain.
        """
        w = weights or DEFAULT_WEIGHTS

        if not abs(sum(w.values()) - 1.0) < 1e-6:
            raise ValueError(f"Weights must sum to 1.0; got {sum(w.values())}")

        score = (
            w["relevance"]   * self.relevance
            + w["recency"]     * self.recency
            + w["provenance"]  * self.provenance
            + w["reliability"] * self.reliability
            + w["cost"]        * self.cost
        )
        self.composite_score = round(score, 4)
        return self.composite_score

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to canonical dict for JSON / on-chain storage."""
        return asdict(self)


def validate_weights(weights: Dict[str, float]) -> None:
    """Confirm weights are well-formed before applying."""
    required = {"relevance", "recency", "provenance", "reliability", "cost"}
    if set(weights.keys()) != required:
        missing = required - set(weights.keys())
        extra   = set(weights.keys()) - required
        raise ValueError(f"Weights mismatch — missing: {missing}, extra: {extra}")
    if not all(0.0 <= v <= 1.0 for v in weights.values()):
        raise ValueError("All weights must be in [0.0, 1.0]")
    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise ValueError(f"Weights must sum to 1.0; got {sum(weights.values())}")
