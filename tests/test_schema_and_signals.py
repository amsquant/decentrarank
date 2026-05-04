"""Tests for the universal schema and signal computation."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decentrarank.schema import Entity, DEFAULT_WEIGHTS, validate_weights
from decentrarank.signals import (
    SignalContext, reliability, cost, recency, provenance, relevance, compute_all_signals,
)


class TestSchema(unittest.TestCase):

    def _make_entity(self, **overrides):
        defaults = dict(
            entity_type   = "validator",
            domain        = "0g.staking",
            producer      = "0xabc",
            submitted_at  = 1_000,
            last_updated  = 2_000,
            relevance     = 0.5,
            recency       = 0.5,
            provenance    = 0.5,
            reliability   = 0.5,
            cost          = 0.5,
        )
        defaults.update(overrides)
        return Entity(**defaults)

    def test_entity_id_is_deterministic(self):
        e1 = self._make_entity()
        e2 = self._make_entity()
        self.assertEqual(e1.entity_id, e2.entity_id)

    def test_entity_id_changes_with_extensions(self):
        e1 = self._make_entity(extensions={"x": 1})
        e2 = self._make_entity(extensions={"x": 2})
        self.assertNotEqual(e1.entity_id, e2.entity_id)

    def test_signal_range_validation(self):
        with self.assertRaises(ValueError):
            self._make_entity(reliability=1.5)
        with self.assertRaises(ValueError):
            self._make_entity(cost=-0.1)

    def test_score_is_weighted_sum(self):
        e = self._make_entity(
            relevance=1.0, recency=0.0,
            provenance=1.0, reliability=0.0, cost=1.0,
        )
        s = e.score(DEFAULT_WEIGHTS)
        # = 0.20*1 + 0.15*0 + 0.20*1 + 0.30*0 + 0.15*1 = 0.55
        self.assertAlmostEqual(s, 0.55, places=4)
        self.assertEqual(e.composite_score, 0.55)

    def test_score_uses_default_weights_implicitly(self):
        e = self._make_entity()
        self.assertAlmostEqual(e.score(), 0.5, places=4)

    def test_invalid_weights_rejected(self):
        with self.assertRaises(ValueError):
            validate_weights({"relevance": 0.5, "recency": 0.5})  # missing keys
        with self.assertRaises(ValueError):
            validate_weights({"relevance": 0.5, "recency": 0.5, "provenance": 0.5,
                              "reliability": 0.5, "cost": 0.5})  # sums to 2.5

    def test_to_dict_roundtrip(self):
        e = self._make_entity(extensions={"foo": "bar"})
        d = e.to_dict()
        self.assertEqual(d["domain"], "0g.staking")
        self.assertEqual(d["extensions"]["foo"], "bar")


class TestSignals(unittest.TestCase):

    def test_reliability_geometric_mean(self):
        ctx = SignalContext(completion_rate=0.99, historical_accuracy=0.99, consistency=0.99)
        self.assertAlmostEqual(reliability(ctx), 0.99, places=2)

    def test_reliability_neutral_with_no_data(self):
        self.assertEqual(reliability(SignalContext()), 0.5)

    def test_cost_lower_is_better(self):
        cheap = SignalContext(cost_value=0.05, cost_max_observed=0.20)
        expensive = SignalContext(cost_value=0.20, cost_max_observed=0.20)
        self.assertGreater(cost(cheap), cost(expensive))

    def test_cost_normalises_to_zero_at_max(self):
        ctx = SignalContext(cost_value=0.20, cost_max_observed=0.20)
        self.assertAlmostEqual(cost(ctx), 0.0, places=4)

    def test_recency_decays_exponentially(self):
        fresh = SignalContext(age_in_units=0,    half_life_units=100)
        stale = SignalContext(age_in_units=200,  half_life_units=100)
        self.assertGreater(recency(fresh), recency(stale))
        self.assertAlmostEqual(recency(fresh), 1.0, places=4)
        self.assertAlmostEqual(recency(stale), 0.25, places=2)

    def test_provenance_verified_bonus(self):
        unverified = SignalContext(producer_reputation=0.6, identity_verified=False)
        verified   = SignalContext(producer_reputation=0.6, identity_verified=True)
        self.assertGreater(provenance(verified), provenance(unverified))
        self.assertAlmostEqual(provenance(verified), 0.7, places=4)

    def test_compute_all_returns_five_signals(self):
        result = compute_all_signals(SignalContext())
        self.assertEqual(set(result.keys()),
                         {"relevance", "recency", "provenance", "reliability", "cost"})


if __name__ == "__main__":
    unittest.main()
