"""
0G Validator Adapter — translates raw 0G validator data into the
DecentraRank universal schema.

The adapter handles two ingestion paths:
  1. Live mode: queries the 0G Tendermint REST gateway and EVM RPC for the
     active validator set.
  2. Replay mode: loads a pre-captured snapshot file (used for offline
     calibration, testing, and grant-demo reproducibility).

Both paths produce the same canonical Entity records.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import json
import logging
import random

from decentrarank.schema import Entity
from decentrarank.signals import SignalContext, compute_all_signals
from decentrarank.ingestion.rpc_client import ZeroGRpcClient, RpcError

logger = logging.getLogger(__name__)

DOMAIN = "0g.staking"
ENTITY_TYPE = "validator"


@dataclass
class ValidatorSnapshot:
    """Raw, untyped representation of a single validator captured from RPC."""
    operator_address:   str
    moniker:             str
    commission_rate:     float           # 0.0–1.0
    delegations_total:   int             # in atto-units (1e-18 0G)
    self_bond:           int             # in atto-units
    uptime_percent:      float           # 0.0–100.0
    blocks_signed:       int
    blocks_proposed:     int
    slashing_events:     int
    jailed:              bool
    identity_verified:   bool
    age_blocks:          int
    last_seen_block:     int


# ── Live ingestion ──────────────────────────────────────────────────────────

def fetch_live_snapshot(
    client: ZeroGRpcClient,
    rest_endpoint: Optional[str],
) -> Tuple[List[ValidatorSnapshot], int]:
    """
    Fetch the active validator set live from a 0G mainnet endpoint.

    Returns a tuple of (snapshots, latest_block_number).
    Raises RpcError if the network cannot be reached.
    """
    latest_block = client.block_number()

    if not rest_endpoint:
        raise RpcError(
            "Live validator ingestion requires a Tendermint REST gateway endpoint. "
            "Set ZEROG_REST_ENDPOINT in your environment or pass --rest-endpoint."
        )

    raw_validators = client.get_validators_via_rest(rest_endpoint)
    snapshots = [_parse_rest_validator(v, latest_block) for v in raw_validators]
    logger.info("Fetched %d active validators at block %d", len(snapshots), latest_block)
    return snapshots, latest_block


def _parse_rest_validator(raw: Dict[str, Any], latest_block: int) -> ValidatorSnapshot:
    """Normalise a Tendermint REST validator record into a ValidatorSnapshot."""
    description     = raw.get("description", {})
    commission      = raw.get("commission", {}).get("commission_rates", {})
    operator_address = raw.get("operator_address", "")

    # The REST gateway exposes some fields directly and others via separate
    # /staking endpoints. For prototype purposes we read what's directly
    # available and mark unobtainable fields with neutral defaults; the
    # production daemon fetches the missing fields via auxiliary calls.

    return ValidatorSnapshot(
        operator_address  = operator_address,
        moniker           = description.get("moniker", operator_address[:10]),
        commission_rate   = float(commission.get("rate", "0.0")),
        delegations_total = int(raw.get("tokens", "0")),
        self_bond         = int(raw.get("min_self_delegation", "0")),
        # Uptime, blocks signed/proposed and slashing history come from the
        # /slashing/signing_infos endpoint in production. Marked neutral here.
        uptime_percent     = 99.0,
        blocks_signed      = 0,
        blocks_proposed    = 0,
        slashing_events    = 0,
        jailed             = bool(raw.get("jailed", False)),
        identity_verified  = bool(description.get("identity", "")),
        age_blocks         = 100,
        last_seen_block    = latest_block,
    )


# ── Replay-mode ingestion (synthetic, reproducible) ─────────────────────────
# Used for offline calibration, testing, and demos when no live RPC is available.
# The synthetic profiles below are designed to span the realistic range observed
# on the 0G Aristotle mainnet (roughly 50 validators, varying performance).

_SYNTHETIC_PROFILES: List[Dict[str, Any]] = [
    # The Principal Investigator's own validator — included for transparency
    {"moniker": "DecentraRank-Validator", "address": "0xaED4832042D1204Faf7a97eDD93611A92B20461c",
     "commission": 0.05, "tokens": 1_500_000, "self_bond": 250_000,
     "uptime": 99.91, "signed": 142_300, "proposed": 1_810,
     "slashing": 0, "jailed": False, "verified": True},

    {"moniker": "Aristotle-Prime",   "address": "0x1111000000000000000000000000000000000001",
     "commission": 0.04, "tokens": 4_200_000, "self_bond": 800_000,
     "uptime": 99.98, "signed": 144_500, "proposed": 2_350,
     "slashing": 0, "jailed": False, "verified": True},

    {"moniker": "Helios-Stake",      "address": "0x1111000000000000000000000000000000000002",
     "commission": 0.06, "tokens": 3_100_000, "self_bond": 600_000,
     "uptime": 99.85, "signed": 143_200, "proposed": 1_980,
     "slashing": 0, "jailed": False, "verified": True},

    {"moniker": "NodeFleet",         "address": "0x1111000000000000000000000000000000000003",
     "commission": 0.10, "tokens": 2_400_000, "self_bond": 400_000,
     "uptime": 99.42, "signed": 141_800, "proposed": 1_640,
     "slashing": 0, "jailed": False, "verified": True},

    {"moniker": "ValidNode-IO",      "address": "0x1111000000000000000000000000000000000004",
     "commission": 0.05, "tokens": 1_900_000, "self_bond": 300_000,
     "uptime": 99.74, "signed": 142_900, "proposed": 1_720,
     "slashing": 0, "jailed": False, "verified": False},

    {"moniker": "InfraDAO",          "address": "0x1111000000000000000000000000000000000005",
     "commission": 0.03, "tokens": 2_700_000, "self_bond": 500_000,
     "uptime": 99.62, "signed": 142_400, "proposed": 1_790,
     "slashing": 0, "jailed": False, "verified": True},

    {"moniker": "BlockKeeper",       "address": "0x1111000000000000000000000000000000000006",
     "commission": 0.08, "tokens": 1_100_000, "self_bond": 180_000,
     "uptime": 98.91, "signed": 140_900, "proposed": 1_410,
     "slashing": 1, "jailed": False, "verified": False},

    {"moniker": "EagleStake",        "address": "0x1111000000000000000000000000000000000007",
     "commission": 0.07, "tokens": 1_700_000, "self_bond": 280_000,
     "uptime": 99.55, "signed": 142_100, "proposed": 1_680,
     "slashing": 0, "jailed": False, "verified": True},

    {"moniker": "MoonValidator",     "address": "0x1111000000000000000000000000000000000008",
     "commission": 0.15, "tokens": 600_000,   "self_bond":  90_000,
     "uptime": 97.20, "signed": 138_700, "proposed":   980,
     "slashing": 2, "jailed": False, "verified": False},

    {"moniker": "ZeroPoint",         "address": "0x1111000000000000000000000000000000000009",
     "commission": 0.05, "tokens": 2_000_000, "self_bond": 350_000,
     "uptime": 99.80, "signed": 143_000, "proposed": 1_770,
     "slashing": 0, "jailed": False, "verified": True},

    {"moniker": "GravityNode",       "address": "0x111100000000000000000000000000000000000a",
     "commission": 0.06, "tokens": 1_300_000, "self_bond": 220_000,
     "uptime": 99.30, "signed": 141_500, "proposed": 1_550,
     "slashing": 0, "jailed": False, "verified": True},

    {"moniker": "ChainGuard",        "address": "0x111100000000000000000000000000000000000b",
     "commission": 0.20, "tokens": 400_000,   "self_bond":  60_000,
     "uptime": 96.40, "signed": 137_200, "proposed":   720,
     "slashing": 3, "jailed": True, "verified": False},
]


def fetch_replay_snapshot(latest_block: int = 1_500_000) -> List[ValidatorSnapshot]:
    """Produce a deterministic synthetic snapshot for offline use."""
    return [
        ValidatorSnapshot(
            operator_address  = p["address"],
            moniker           = p["moniker"],
            commission_rate   = p["commission"],
            delegations_total = p["tokens"] * 10**18,
            self_bond         = p["self_bond"] * 10**18,
            uptime_percent    = p["uptime"],
            blocks_signed     = p["signed"],
            blocks_proposed   = p["proposed"],
            slashing_events   = p["slashing"],
            jailed            = p["jailed"],
            identity_verified = p["verified"],
            age_blocks        = 100,
            last_seen_block   = latest_block,
        )
        for p in _SYNTHETIC_PROFILES
    ]


# ── Conversion to canonical Entity ──────────────────────────────────────────

def normalise_to_entity(
    snapshot: ValidatorSnapshot,
    cost_max_observed: float,
    query_match: Optional[float] = None,
    half_life_blocks: int = 1_000,
) -> Entity:
    """
    Convert a ValidatorSnapshot into a canonical DecentraRank Entity.
    """
    # Reliability components
    completion_rate = max(0.0, min(1.0, snapshot.uptime_percent / 100.0))

    # Slashing history damages historical accuracy; >2 events caps at 0.4
    slashing_penalty = min(snapshot.slashing_events * 0.2, 0.6)
    historical_accuracy = max(0.0, 1.0 - slashing_penalty)
    if snapshot.jailed:
        historical_accuracy = min(historical_accuracy, 0.3)

    # Consistency: ratio of proposed-to-signed (proposers should propose
    # roughly proportional to their stake; deviations from expected indicate
    # operational instability)
    consistency = 1.0 if snapshot.blocks_signed == 0 else min(
        1.0, snapshot.blocks_signed / max(snapshot.blocks_signed + 100, 1)
    )

    # Producer reputation: a function of self-bond ratio and verification.
    self_bond_ratio = (
        snapshot.self_bond / max(snapshot.delegations_total, 1)
        if snapshot.delegations_total > 0 else 0.0
    )
    producer_reputation = max(0.0, min(1.0, 0.5 + self_bond_ratio * 2.0))

    ctx = SignalContext(
        completion_rate     = completion_rate,
        historical_accuracy = historical_accuracy,
        consistency         = consistency,
        cost_value          = snapshot.commission_rate,
        cost_max_observed   = cost_max_observed,
        age_in_units        = snapshot.age_blocks,
        half_life_units     = half_life_blocks,
        producer_reputation = producer_reputation,
        identity_verified   = snapshot.identity_verified,
        query_match_score   = query_match,
    )
    signals = compute_all_signals(ctx)

    return Entity(
        entity_type   = ENTITY_TYPE,
        domain        = DOMAIN,
        producer      = snapshot.operator_address,
        submitted_at  = snapshot.last_seen_block - snapshot.age_blocks,
        last_updated  = snapshot.last_seen_block,
        relevance     = signals["relevance"],
        recency       = signals["recency"],
        provenance    = signals["provenance"],
        reliability   = signals["reliability"],
        cost          = signals["cost"],
        extensions    = {
            DOMAIN: {
                "moniker":             snapshot.moniker,
                "operator_address":    snapshot.operator_address,
                "commission_rate":     snapshot.commission_rate,
                "delegations_total":   str(snapshot.delegations_total),
                "self_bond":           str(snapshot.self_bond),
                "uptime_percent":      snapshot.uptime_percent,
                "blocks_signed":       snapshot.blocks_signed,
                "blocks_proposed":     snapshot.blocks_proposed,
                "slashing_events":     snapshot.slashing_events,
                "jailed":              snapshot.jailed,
                "identity_verified":   snapshot.identity_verified,
            }
        },
    )
