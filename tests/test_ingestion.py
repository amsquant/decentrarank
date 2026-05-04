"""Tests for the ingestion pipeline and validator adapter."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decentrarank.ingestion.pipeline import run_ingestion
from decentrarank.ingestion.validator_adapter import (
    fetch_replay_snapshot, normalise_to_entity,
)


class TestReplayIngestion(unittest.TestCase):

    def test_replay_snapshot_is_non_empty(self):
        snaps = fetch_replay_snapshot()
        self.assertGreaterEqual(len(snaps), 5)

    def test_replay_includes_pi_validator(self):
        snaps = fetch_replay_snapshot()
        addresses = [s.operator_address for s in snaps]
        self.assertIn("0xaED4832042D1204Faf7a97eDD93611A92B20461c", addresses)

    def test_normalise_produces_valid_entity(self):
        snap = fetch_replay_snapshot()[0]
        cost_max = max(s.commission_rate for s in fetch_replay_snapshot())
        entity = normalise_to_entity(snap, cost_max_observed=cost_max)
        self.assertEqual(entity.entity_type, "validator")
        self.assertEqual(entity.domain, "0g.staking")
        self.assertIn("0g.staking", entity.extensions)
        self.assertTrue(0.0 <= entity.reliability <= 1.0)

    def test_jailed_validator_has_low_score(self):
        snaps = fetch_replay_snapshot()
        cost_max = max(s.commission_rate for s in snaps)
        entities = [normalise_to_entity(s, cost_max_observed=cost_max) for s in snaps]
        for e in entities:
            e.score()
        # The jailed validator should not be top-1.
        entities.sort(key=lambda e: e.composite_score or 0.0, reverse=True)
        top1 = entities[0]
        self.assertFalse(top1.extensions["0g.staking"].get("jailed", False))


class TestPipelineEnd2End(unittest.TestCase):

    def test_replay_pipeline_returns_ranked_entities(self):
        result = run_ingestion(force_replay=True)
        self.assertEqual(result.source, "replay")
        self.assertGreater(len(result.entities), 0)
        # Verify rankings are non-decreasing in score (descending order)
        scores = [e.composite_score for e in result.entities]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_pi_validator_ranks_well(self):
        """The PI's validator has good metrics; should be in the top half."""
        result = run_ingestion(force_replay=True)
        names = [e.extensions["0g.staking"]["moniker"] for e in result.entities]
        pi_pos = names.index("DecentraRank-Validator")
        self.assertLess(pi_pos, len(names) // 2,
                        f"DecentraRank-Validator at position {pi_pos} of {len(names)}")


if __name__ == "__main__":
    unittest.main()
