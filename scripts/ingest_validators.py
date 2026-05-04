#!/usr/bin/env python3
"""
ingest_validators.py — production-grade ingestion script for the 0G validator set.

Usage examples:

  # Live mode (production)
  export ZEROG_RPC_ENDPOINT="https://your-0g-rpc"
  export ZEROG_REST_ENDPOINT="https://your-0g-rest-gateway"
  python scripts/ingest_validators.py

  # Replay mode (offline / for grant demo)
  python scripts/ingest_validators.py --replay

  # Custom output file
  python scripts/ingest_validators.py --replay --output build/snapshot.json
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the package importable when running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decentrarank.ingestion.pipeline import run_ingestion
from decentrarank import __version__


def main() -> int:
    parser = argparse.ArgumentParser(description="DecentraRank — 0G validator ingestion")
    parser.add_argument("--rpc-endpoint",  help="0G mainnet JSON-RPC endpoint (or set $ZEROG_RPC_ENDPOINT)")
    parser.add_argument("--rest-endpoint", help="0G Tendermint REST gateway (or set $ZEROG_REST_ENDPOINT)")
    parser.add_argument("--replay", action="store_true", help="Use replay snapshot instead of live RPC")
    parser.add_argument("--output",  default="build/validator_index.json", help="Output JSON path")
    parser.add_argument("--limit",   type=int, default=20, help="Limit number of validators printed to stdout")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print(f"\nDecentraRank v{__version__} — 0G Validator Ingestion")
    print("=" * 72)

    result = run_ingestion(
        rpc_endpoint  = args.rpc_endpoint,
        rest_endpoint = args.rest_endpoint,
        force_replay  = args.replay,
    )

    print(f"  Source       : {result.source.upper()}")
    print(f"  Block number : {result.block_number}")
    print(f"  Validators   : {len(result.entities)}")
    print(f"  Generated at : {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print("=" * 72)

    # Pretty print the ranked table
    header = f"{'Rank':<5} {'Validator':<26} {'Score':>7} {'Rel.':>5} {'Cost':>5} {'Prov.':>6} {'Slash':>5}"
    print(header)
    print("-" * len(header))
    for i, e in enumerate(result.entities[:args.limit], start=1):
        ext = e.extensions.get("0g.staking", {})
        moniker = (ext.get("moniker") or e.entity_id or "?")[:24]
        slashing = ext.get("slashing_events", 0)
        jailed = " J" if ext.get("jailed") else ""
        marker = "[1]" if i == 1 else "[2]" if i == 2 else "[3]" if i == 3 else f" {i:>2}"
        print(
            f"{marker:<5} {moniker + jailed:<26} "
            f"{e.composite_score:>7.4f} "
            f"{e.reliability:>5.2f} "
            f"{e.cost:>5.2f} "
            f"{e.provenance:>6.2f} "
            f"{slashing:>5}"
        )
    if len(result.entities) > args.limit:
        print(f"  ... ({len(result.entities) - args.limit} more)")

    # Write JSON output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "0.1.0",
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "source":         result.source,
        "block_number":   result.block_number,
        "validator_count": len(result.entities),
        "rankings": [e.to_dict() for e in result.entities],
    }
    output_path.write_text(json.dumps(payload, indent=2))
    print(f"\n  Output written to: {output_path.resolve()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
