"""
DecentraRank Multi-Agent Based Simulation — agent definitions.

Three agent types matching Section 5.2 of the grant proposal:

  1. ProducerAgent       — service providers (validators) competing for demand
  2. ConsumerAgent       — service consumers (delegators) selecting providers
  3. ValidatorOfValidatorsAgent — observers monitoring producer behaviour and
                                  surfacing reputation signals

Agents are intentionally simple: behavioural rules are explicit and auditable,
which is essential for a research model whose outputs must be reproducible.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import random


# ── ProducerAgent ─────────────────────────────────────────────────────────────

@dataclass
class ProducerAgent:
    """
    Models a service provider competing for consumer demand.

    Key parameters control its true (hidden) quality and economic strategy.
    The simulation reveals these to consumers gradually through observed
    interaction outcomes — never directly.
    """
    name:                   str

    # Hidden ground-truth parameters
    base_reliability:       float    # 0.0–1.0, true reliability
    base_quality:           float    # 0.0–1.0, true output quality
    base_cost:              float    # 0.0–1.0, normalised commission/fee
    is_adversarial:         bool = False    # if True, occasionally misbehaves

    # Public-facing strategy (can shift each step)
    advertised_cost:        Optional[float] = None  # may differ from base

    # Accumulated observable history (what consumers actually see)
    selections_received:    int = 0
    successful_outcomes:    int = 0
    failed_outcomes:        int = 0
    lifetime_revenue:       float = 0.0
    detected_misbehaviours: int = 0

    def serve_request(self, rng: random.Random) -> Tuple[bool, float]:
        """
        Handle a consumer request. Returns (success, observed_quality).
        Adversarial producers sometimes fail or produce low-quality output
        even when their stated reliability is high.
        """
        self.selections_received += 1

        effective_reliability = self.base_reliability
        if self.is_adversarial and rng.random() < 0.15:
            effective_reliability *= 0.4

        success = rng.random() < effective_reliability
        if success:
            quality = max(0.0, min(1.0, rng.gauss(self.base_quality, 0.05)))
            self.successful_outcomes += 1
            self.lifetime_revenue += self.advertised_cost or self.base_cost
            return True, quality
        else:
            self.failed_outcomes += 1
            return False, 0.0

    @property
    def observed_reliability(self) -> float:
        """Reliability as observed externally — what consumers can compute."""
        total = self.selections_received
        return self.successful_outcomes / total if total > 0 else 0.5


# ── ConsumerAgent ────────────────────────────────────────────────────────────

@dataclass
class ConsumerAgent:
    """
    Models a service consumer with private preferences and a learning rule.

    Consumers maintain beliefs about each producer and update them after each
    interaction. They use an epsilon-greedy strategy: most of the time they
    pick the producer they believe is best, but occasionally they explore.
    """
    name:                   str

    # Private preferences — what this consumer values
    weight_reliability:     float
    weight_cost:            float
    weight_quality:         float

    # Learning behaviour
    exploration_rate:       float = 0.15
    learning_rate:          float = 0.20

    # Accumulated beliefs about each producer (keyed by producer name)
    beliefs:                Dict[str, Dict[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalise weights to sum to 1.
        total = self.weight_reliability + self.weight_cost + self.weight_quality
        if total <= 0:
            raise ValueError(f"{self.name}: weights must be positive")
        self.weight_reliability /= total
        self.weight_cost        /= total
        self.weight_quality     /= total

    def _expected_value(self, producer_name: str, advertised_cost: float) -> float:
        """Compute the consumer's expected value for selecting a given producer."""
        belief = self.beliefs.get(
            producer_name,
            {"reliability": 0.5, "quality": 0.5},
        )
        cost_score = max(0.0, 1.0 - advertised_cost)
        return (
            self.weight_reliability * belief["reliability"]
            + self.weight_quality   * belief["quality"]
            + self.weight_cost      * cost_score
        )

    def select_producer(
        self,
        producers: List[ProducerAgent],
        rng:       random.Random,
    ) -> ProducerAgent:
        """Choose a producer using an epsilon-greedy strategy."""
        # Filter out producers that have been flagged as misbehaving repeatedly
        eligible = [p for p in producers if p.detected_misbehaviours < 5]
        if not eligible:
            eligible = producers
        if rng.random() < self.exploration_rate:
            return rng.choice(eligible)
        return max(
            eligible,
            key=lambda p: self._expected_value(p.name, p.advertised_cost or p.base_cost),
        )

    def update_belief(
        self,
        producer:        ProducerAgent,
        success:         bool,
        observed_quality: float,
    ) -> None:
        """Bayesian-style belief update with learning_rate as the step size."""
        prev = self.beliefs.get(
            producer.name,
            {"reliability": 0.5, "quality": 0.5},
        )
        reliability_signal = 1.0 if success else 0.0
        quality_signal     = observed_quality if success else prev["quality"]
        self.beliefs[producer.name] = {
            "reliability": prev["reliability"] + self.learning_rate * (reliability_signal - prev["reliability"]),
            "quality":     prev["quality"]     + self.learning_rate * (quality_signal     - prev["quality"]),
        }


# ── ValidatorOfValidatorsAgent ───────────────────────────────────────────────

@dataclass
class ValidatorOfValidatorsAgent:
    """
    Network observer agent. Monitors all producer-consumer interactions and
    flags producers whose observed behaviour materially diverges from their
    advertised behaviour.

    In a real network this role is performed by validators monitoring each
    other (slashing modules, missed-block detection) and by independent
    auditors. The simulation models this as a single observer with full
    transaction visibility.
    """
    name:                  str
    detection_threshold:   float = 0.30  # if observed reliability falls
                                          # this far below the advertised
                                          # rate, flag the producer.

    flagged_history:       List[Tuple[int, str, str]] = field(default_factory=list)
    # Each entry: (step, producer_name, reason)

    def observe_step(
        self,
        step:      int,
        producers: List[ProducerAgent],
    ) -> None:
        """Run the observer's detection rules at the end of each simulation step."""
        for p in producers:
            # Only evaluate producers with enough observations.
            if p.selections_received < 10:
                continue

            advertised = p.base_reliability
            observed   = p.observed_reliability
            if advertised - observed > self.detection_threshold:
                # Flag and increment the producer's misbehaviour counter.
                p.detected_misbehaviours += 1
                self.flagged_history.append(
                    (step, p.name,
                     f"observed reliability {observed:.2f} below advertised {advertised:.2f}")
                )
