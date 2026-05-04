"""
DecentraRank MABS — weight calibration loop.

Calibration runs many simulations with different signal weights and selects
the weights that maximise stability and consumer satisfaction. This is the
research contribution of the project: ranking weights are not hand-tuned;
they are derived from emergent agent behaviour.

The procedure is intentionally simple and transparent:
  1. Sample candidate weight vectors from a Dirichlet-like grid.
  2. For each candidate, run a full simulation against a fixed scenario.
  3. Score each candidate by:
       (a) ranking stability — how stable is the top-N ordering?
       (b) consumer satisfaction — how many consumer expectations are met?
       (c) adversarial penalty — are misbehaving producers correctly demoted?
  4. Return the best-scoring weight vector and full search history.

Note: the calibration search space is the per-domain composite-score weights
applied at the universal-schema layer (see SCHEMA.md §"Composite scoring").
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import copy
import itertools
import random

from decentrarank.mabs.agents import ProducerAgent, ConsumerAgent, ValidatorOfValidatorsAgent
from decentrarank.mabs.simulation import (
    SimulationConfig,
    SimulationResult,
    run_simulation,
    scenario_from_validators,
)
from decentrarank.schema import Entity


@dataclass
class CalibrationResult:
    best_weights:     Dict[str, float]
    best_score:       float
    search_history:   List[Tuple[Dict[str, float], float]]


def _generate_weight_grid(step: float = 0.10) -> List[Dict[str, float]]:
    """
    Enumerate weight vectors over the 5 universal signals that sum to 1.0,
    in increments of `step`. With step=0.10 this yields a few hundred
    candidates — enough for a meaningful search without being expensive.
    """
    n_steps = int(round(1.0 / step))
    grid: List[Dict[str, float]] = []
    for w1, w2, w3, w4 in itertools.product(range(n_steps + 1), repeat=4):
        if w1 + w2 + w3 + w4 > n_steps:
            continue
        w5 = n_steps - (w1 + w2 + w3 + w4)
        if w5 < 0:
            continue
        # Skip vectors that have any zero — calibration favours weight
        # spreads where every signal contributes at least a little.
        if min(w1, w2, w3, w4, w5) == 0:
            continue
        grid.append({
            "relevance":   w1 * step,
            "recency":     w2 * step,
            "provenance":  w3 * step,
            "reliability": w4 * step,
            "cost":        w5 * step,
        })
    return grid


def _stability_score(result: SimulationResult, top_n: int = 5, last_k: int = 30) -> float:
    """How stable is the top-N ordering across the last K steps?"""
    logs = result.step_logs[-last_k:]
    if len(logs) < 2:
        return 0.0
    # Average overlap of top-N sets between consecutive steps.
    overlaps: List[float] = []
    for a, b in zip(logs, logs[1:]):
        set_a = {n for n, _ in a.rankings[:top_n]}
        set_b = {n for n, _ in b.rankings[:top_n]}
        if not set_a:
            continue
        overlaps.append(len(set_a & set_b) / top_n)
    return sum(overlaps) / len(overlaps) if overlaps else 0.0


def _consumer_satisfaction(result: SimulationResult) -> float:
    """
    What fraction of total consumer requests resulted in successful outcomes?
    This is a proxy for whether the rankings are leading consumers to
    high-quality producers.
    """
    successes = sum(p.successful_outcomes for p in result.producers)
    total = sum(p.selections_received for p in result.producers)
    return successes / total if total > 0 else 0.0


def _adversarial_demotion(result: SimulationResult, top_n: int = 5) -> float:
    """
    Of the producers flagged adversarial in the ground truth, how many are
    successfully kept *out* of the top N at the end of the simulation?
    Returns 1.0 if all adversaries are demoted, 0.0 if none are.
    """
    adversaries = {p.name for p in result.producers if p.is_adversarial}
    if not adversaries:
        return 1.0  # no adversaries → vacuously perfect
    final_top_n = {n for n, _ in result.final_rankings()[:top_n]}
    correctly_demoted = adversaries - final_top_n
    return len(correctly_demoted) / len(adversaries)


def evaluate_candidate(
    weights:   Dict[str, float],
    entities:  List[Entity],
    n_consumers: int = 12,
    config:    Optional[SimulationConfig] = None,
) -> Tuple[float, SimulationResult]:
    """
    Run a simulation under the candidate weights and return a composite
    objective score plus the simulation result.
    """
    config = config or SimulationConfig()

    # Recompute composite scores under candidate weights — affects which
    # entities the simulation perceives as ranked highest, but agent
    # behaviour itself is independent of the schema-level weights.
    for e in entities:
        e.score(weights)

    producers, consumers, observer = scenario_from_validators(
        entities, n_consumers=n_consumers, seed=config.seed,
    )
    # Bias consumer preferences toward the candidate's weight emphasis.
    for c in consumers:
        # Map schema weights onto consumer behaviour: consumers care about
        # reliability and cost weights directly; provenance maps to quality.
        total = weights["reliability"] + weights["cost"] + weights["provenance"]
        if total > 0:
            c.weight_reliability = weights["reliability"] / total
            c.weight_cost        = weights["cost"]        / total
            c.weight_quality     = weights["provenance"]  / total

    result = run_simulation(producers, consumers, observer, config)

    stability     = _stability_score(result)
    satisfaction  = _consumer_satisfaction(result)
    adversarial   = _adversarial_demotion(result)
    composite     = 0.4 * stability + 0.4 * satisfaction + 0.2 * adversarial

    return round(composite, 4), result


def calibrate(
    entities:    List[Entity],
    grid_step:   float = 0.10,
    config:      Optional[SimulationConfig] = None,
    n_top:       int   = 5,
) -> CalibrationResult:
    """
    Run the full calibration sweep and return the best-scoring weights.
    """
    grid = _generate_weight_grid(grid_step)
    history: List[Tuple[Dict[str, float], float]] = []

    for weights in grid:
        score, _result = evaluate_candidate(weights, entities, config=config)
        history.append((weights, score))

    history.sort(key=lambda t: t[1], reverse=True)
    best_weights, best_score = history[0]

    return CalibrationResult(
        best_weights   = best_weights,
        best_score     = best_score,
        search_history = history,   # keep all candidates for downstream analysis
    )
