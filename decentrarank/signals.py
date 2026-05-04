"""
DecentraRank Universal Signals — computation of the five core ranking signals.

Each signal is computed from raw domain data and normalised to [0.0, 1.0].
The signal computations themselves are domain-agnostic; domain adapters
provide the input data shape.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import math


@dataclass
class SignalContext:
    """
    Context required to compute universal signals for a single entity.

    Adapters populate this from their domain-specific inputs. Fields that do
    not apply to a given domain are left at their default and contribute
    neutrally to the composite score.
    """
    # Reliability inputs
    completion_rate:      Optional[float] = None  # 0.0–1.0
    historical_accuracy:  Optional[float] = None  # 0.0–1.0
    consistency:          Optional[float] = None  # 0.0–1.0

    # Cost inputs
    cost_value:           Optional[float] = None  # raw cost
    cost_max_observed:    Optional[float] = None  # for normalisation

    # Recency inputs
    age_in_units:         Optional[int]   = None  # how stale is this record
    half_life_units:      Optional[int]   = None  # domain-specific decay

    # Provenance inputs
    producer_reputation:  Optional[float] = None  # 0.0–1.0
    identity_verified:    bool = False

    # Relevance inputs
    query_match_score:    Optional[float] = None  # 0.0–1.0


def reliability(ctx: SignalContext) -> float:
    """
    Reliability is the geometric mean of available reliability indicators.
    Geometric mean is used because reliability components are multiplicative:
    a system that is 99% available but produces 50% accurate output is not
    "75% reliable" — it is closer to 50% reliable.
    """
    components = [
        ctx.completion_rate,
        ctx.historical_accuracy,
        ctx.consistency,
    ]
    available = [c for c in components if c is not None]
    if not available:
        return 0.5  # neutral if no data
    product = 1.0
    for c in available:
        product *= max(c, 1e-6)
    return product ** (1 / len(available))


def cost(ctx: SignalContext) -> float:
    """
    Cost signal: lower cost yields higher score.
    Normalised against the maximum observed cost in the domain.
    """
    if ctx.cost_value is None or ctx.cost_max_observed is None:
        return 0.5
    if ctx.cost_max_observed <= 0:
        return 1.0
    normalised = min(ctx.cost_value / ctx.cost_max_observed, 1.0)
    return max(0.0, 1.0 - normalised)


def recency(ctx: SignalContext) -> float:
    """
    Exponential decay with a domain-specific half-life.
    """
    if ctx.age_in_units is None or ctx.half_life_units is None:
        return 0.5
    if ctx.half_life_units <= 0:
        return 1.0
    decay_rate = math.log(2) / ctx.half_life_units
    return math.exp(-decay_rate * ctx.age_in_units)


def provenance(ctx: SignalContext) -> float:
    """
    Provenance combines producer reputation with identity verification.
    Verified identity adds a 10% bonus to producer reputation, capped at 1.0.
    """
    base = ctx.producer_reputation if ctx.producer_reputation is not None else 0.5
    bonus = 0.10 if ctx.identity_verified else 0.0
    return min(1.0, base + bonus)


def relevance(ctx: SignalContext) -> float:
    """
    Relevance is provided by the adapter as a query-context match score.
    In the absence of a query context, returns a neutral value.
    """
    return ctx.query_match_score if ctx.query_match_score is not None else 0.5


def compute_all_signals(ctx: SignalContext) -> Dict[str, float]:
    """Compute all five universal signals for a single entity."""
    return {
        "relevance":   relevance(ctx),
        "recency":     recency(ctx),
        "provenance":  provenance(ctx),
        "reliability": reliability(ctx),
        "cost":        cost(ctx),
    }
