"""
End-to-end ingestion pipeline.

Pulls validators from either a live 0G mainnet endpoint or a replay snapshot,
normalises them through the universal schema, computes ranking signals, and
produces a ranked output ready for the query layer.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import logging
import os

from decentrarank.schema import Entity, DEFAULT_WEIGHTS
from decentrarank.ingestion.rpc_client import ZeroGRpcClient, RpcConfig, RpcError
from decentrarank.ingestion.validator_adapter import (
    fetch_live_snapshot,
    fetch_replay_snapshot,
    normalise_to_entity,
    ValidatorSnapshot,
)

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Output of a single ingestion run."""
    entities:         List[Entity]
    source:           str       # "live" or "replay"
    block_number:     int
    rest_endpoint:    Optional[str] = None


def run_ingestion(
    rpc_endpoint:  Optional[str] = None,
    rest_endpoint: Optional[str] = None,
    force_replay:  bool = False,
) -> IngestionResult:
    """
    Run the full ingestion pipeline.

    Resolution order:
      1. If force_replay=True, use synthetic snapshot.
      2. If rpc_endpoint provided, attempt live ingestion.
      3. On any RPC failure, fall back to replay (logged as a warning).
    """
    snapshots: List[ValidatorSnapshot]
    block_number: int
    source: str

    rpc_endpoint  = rpc_endpoint  or os.environ.get("ZEROG_RPC_ENDPOINT")
    rest_endpoint = rest_endpoint or os.environ.get("ZEROG_REST_ENDPOINT")

    if force_replay or not rpc_endpoint:
        if not force_replay:
            logger.info("No RPC endpoint configured; using replay snapshot.")
        snapshots    = fetch_replay_snapshot()
        block_number = snapshots[0].last_seen_block if snapshots else 0
        source       = "replay"
    else:
        try:
            client = ZeroGRpcClient(RpcConfig(endpoint=rpc_endpoint))
            chain_id = client.chain_id()
            logger.info("Connected to 0G chain %d via %s", chain_id, rpc_endpoint)
            snapshots, block_number = fetch_live_snapshot(client, rest_endpoint)
            source = "live"
        except RpcError as e:
            logger.warning("Live ingestion failed (%s); falling back to replay.", e)
            snapshots    = fetch_replay_snapshot()
            block_number = snapshots[0].last_seen_block if snapshots else 0
            source       = "replay"

    # Normalise to entities — cost normalisation requires the max commission
    # rate observed across the snapshot.
    cost_max = max((s.commission_rate for s in snapshots), default=0.20)
    entities = [
        normalise_to_entity(s, cost_max_observed=cost_max)
        for s in snapshots
    ]

    # Compute composite scores.
    for e in entities:
        e.score(DEFAULT_WEIGHTS)

    # Rank descending by composite score.
    entities.sort(key=lambda e: e.composite_score or 0.0, reverse=True)

    return IngestionResult(
        entities      = entities,
        source        = source,
        block_number  = block_number,
        rest_endpoint = rest_endpoint,
    )
