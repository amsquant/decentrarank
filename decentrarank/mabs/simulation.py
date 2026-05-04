"""
DecentraRank MABS — simulation engine.

Drives the three agent types through discrete time steps and records full
state for downstream calibration analysis.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import random
import statistics

from decentrarank.mabs.agents import (
    ProducerAgent,
    ConsumerAgent,
    ValidatorOfValidatorsAgent,
)
from decentrarank.schema import Entity


@dataclass
class SimulationConfig:
    n_steps:              int   = 100
    requests_per_step:    int   = 12
    seed:                 int   = 42


@dataclass
class StepLog:
    step:                 int
    rankings:             List[Tuple[str, float]]   # (producer_name, score), descending
    flagged_this_step:    List[str]


@dataclass
class SimulationResult:
    config:               SimulationConfig
    producers:            List[ProducerAgent]
    consumers:            List[ConsumerAgent]
    observer:             ValidatorOfValidatorsAgent
    step_logs:            List[StepLog] = field(default_factory=list)

    def final_rankings(self) -> List[Tuple[str, float]]:
        if not self.step_logs:
            return []
        return self.step_logs[-1].rankings

    def convergence_step(self, window: int = 10) -> Optional[int]:
        """The first step at which the top-1 producer remains stable for `window` steps."""
        if len(self.step_logs) < window:
            return None
        for i in range(window, len(self.step_logs)):
            top1s = {self.step_logs[j].rankings[0][0] for j in range(i - window, i)}
            if len(top1s) == 1:
                return i - window + 1
        return None


def _producers_to_entities(producers: List[ProducerAgent]) -> List[Tuple[str, float]]:
    """
    Compute a snapshot ranking from current producer state.
    Composite is a weighted mix that mirrors the universal-signal approach,
    using observed (not hidden) reliability so consumers and the simulation
    agree on how producers compare.
    """
    rankings: List[Tuple[str, float]] = []
    for p in producers:
        if p.selections_received == 0:
            score = 0.5
        else:
            obs_rel  = p.observed_reliability
            cost_sc  = max(0.0, 1.0 - (p.advertised_cost or p.base_cost))
            penalty  = min(p.detected_misbehaviours * 0.10, 0.5)
            score    = max(0.0, 0.6 * obs_rel + 0.3 * cost_sc - penalty + 0.1)
        rankings.append((p.name, round(score, 4)))
    rankings.sort(key=lambda x: x[1], reverse=True)
    return rankings


def run_simulation(
    producers: List[ProducerAgent],
    consumers: List[ConsumerAgent],
    observer:  ValidatorOfValidatorsAgent,
    config:    SimulationConfig,
) -> SimulationResult:
    """Execute the full simulation and return the recorded result."""
    rng = random.Random(config.seed)

    # Initialise advertised cost = base cost for all producers.
    for p in producers:
        if p.advertised_cost is None:
            p.advertised_cost = p.base_cost

    result = SimulationResult(
        config    = config,
        producers = producers,
        consumers = consumers,
        observer  = observer,
    )

    for step in range(1, config.n_steps + 1):
        flagged_before = len(observer.flagged_history)

        for _ in range(config.requests_per_step):
            consumer = rng.choice(consumers)
            producer = consumer.select_producer(producers, rng)
            success, quality = producer.serve_request(rng)
            consumer.update_belief(producer, success, quality)

        # Observer pass at end of step
        observer.observe_step(step, producers)

        # Snapshot ranking
        rankings = _producers_to_entities(producers)
        flagged_this_step = [
            entry[1] for entry in observer.flagged_history[flagged_before:]
        ]
        result.step_logs.append(StepLog(
            step              = step,
            rankings          = rankings,
            flagged_this_step = flagged_this_step,
        ))

    return result


# ── Scenario builders ────────────────────────────────────────────────────────

def scenario_from_validators(
    entities: List[Entity],
    n_consumers: int = 12,
    seed:        int = 42,
) -> Tuple[List[ProducerAgent], List[ConsumerAgent], ValidatorOfValidatorsAgent]:
    """
    Construct a simulation scenario from a list of validator entities.

    Each entity becomes a ProducerAgent whose hidden parameters are derived
    from the universal signals already computed by the ingestion pipeline.
    """
    rng = random.Random(seed)
    producers: List[ProducerAgent] = []

    for e in entities:
        ext = e.extensions.get("0g.staking", {})
        # Adversarial flag: jailed validators or high slashing counts.
        adversarial = bool(ext.get("jailed")) or ext.get("slashing_events", 0) >= 2
        producers.append(ProducerAgent(
            name             = ext.get("moniker", e.entity_id or "unknown"),
            base_reliability = e.reliability,
            base_quality     = e.provenance,        # treat provenance as quality proxy
            base_cost        = ext.get("commission_rate", 0.10),
            is_adversarial   = adversarial,
        ))

    # Build consumers with diverse preference profiles.
    profiles = [
        # (reliability_weight, cost_weight, quality_weight) — three archetypes
        (0.7, 0.2, 0.1),   # reliability-focused (institutional delegators)
        (0.3, 0.5, 0.2),   # cost-focused (retail delegators)
        (0.5, 0.2, 0.3),   # balanced
    ]
    consumers: List[ConsumerAgent] = []
    for i in range(n_consumers):
        rel_w, cost_w, qual_w = rng.choice(profiles)
        consumers.append(ConsumerAgent(
            name              = f"Delegator-{i+1:02d}",
            weight_reliability = rel_w,
            weight_cost        = cost_w,
            weight_quality     = qual_w,
        ))

    observer = ValidatorOfValidatorsAgent(name="0G-NetworkObserver")
    return producers, consumers, observer
