> **Active 0G Mainnet Validator** — this project is built and operated by an active validator on 0G mainnet (chain ID 16661).
> Validator address: [`0xaED4832042D1204Faf7a97eDD93611A92B20461c`](https://chainscan.0g.ai/address/0xaED4832042D1204Faf7a97eDD93611A92B20461c)
>
> Live RPC connection verified. See [`build/live_run.log`](build/live_run.log) for the captured connection log.
# DecentraRank

> Universal AI-powered ranking & indexing infrastructure for the 0G Network.

This repository contains the production-grade prototype that accompanies the
DecentraRank Guild on 0G 2.0 grant proposal.

## What's in here

```
decentrarank/
├── INDEX_DECISION.md             # Why we index validators first
├── SCHEMA.md                     # Universal schema specification
├── README.md                     # This file
├── requirements.txt
├── decentrarank/
│   ├── schema.py                 # Canonical Entity dataclass
│   ├── signals.py                # Five universal ranking signals
│   ├── ingestion/
│   │   ├── rpc_client.py         # 0G JSON-RPC client (retries, backoff)
│   │   ├── validator_adapter.py  # 0G validator → universal Entity
│   │   └── pipeline.py           # End-to-end ingestion pipeline
│   └── mabs/
│       ├── agents.py             # 3-agent architecture
│       ├── simulation.py         # Discrete-step simulation engine
│       └── calibration.py        # Weight-calibration sweep
├── scripts/
│   ├── ingest_validators.py      # Run the ingestion pipeline
│   └── run_simulation.py         # Run MABS + calibration end-to-end
└── tests/
    ├── test_schema_and_signals.py
    └── test_ingestion.py
```

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the ingestion pipeline (replay mode — no network access required)
python scripts/ingest_validators.py --replay

# 3. Run the full MABS simulation + calibration
python scripts/run_simulation.py --replay --steps 100

# 4. Run the test suite
python -m unittest discover tests -v
```

## Live mode

To run against a live 0G mainnet endpoint, configure both the JSON-RPC and
the Tendermint REST gateway endpoints:

```bash
export ZEROG_RPC_ENDPOINT="https://your-0g-rpc"
export ZEROG_REST_ENDPOINT="https://your-0g-rest-gateway"

python scripts/ingest_validators.py
python scripts/run_simulation.py --steps 200
```

If the RPC endpoint is unreachable or the REST gateway is not configured,
the pipeline falls back gracefully to replay mode and clearly logs that it
has done so.

## Architecture overview

**Three layers, each leveraging 0G's modular infrastructure:**

1. **Universal Ingestion & Adapter Framework** — domain-specific adapters
   translate any structured dataset into a single canonical schema. The
   validator adapter is the reference implementation. Adapters for DeFi,
   DeSci, and AI-agent domains follow the same pattern.

2. **MABS Ranking Engine** — three agent types (`ProducerAgent`,
   `ConsumerAgent`, `ValidatorOfValidatorsAgent`) interact under
   configurable rules, and ranking weights are derived from the emergent
   stability of those interactions rather than hand-coded.

3. **Verifiable Persistence on 0G** — entity records are content-addressable
   and designed to be persisted on 0G Storage with proofs in the 0G DA
   layer. This prototype produces JSON output ready for storage submission;
   the production daemon (Milestone 2) wires it to the live 0G stack.

## What's prototype vs production

This codebase is a working prototype at v0.1. The grant funds:

- **Milestone 1** — schema lock at v1.0; production-grade adapters for two
  more verticals; full integration test suite.
- **Milestone 2** — MABS engine deployed to production with the calibration
  loop running continuously; live integration with 0G Storage and DA.
- **Milestone 3** — public REST + GraphQL query API; verifiable execution
  via 0G Compute; security audit.
- **Milestone 4** — open-source release; deployment guide; research paper
  draft.

## License

All code: Apache License 2.0
All documentation and research outputs: CC-BY-4.0

## Contact

Hanumant Joshi — hanumantjoshi44@gmail.com

Validator address (active on 0G mainnet):
[`0xaED4832042D1204Faf7a97eDD93611A92B20461c`](https://chainscan.0g.ai/address/0xaED4832042D1204Faf7a97eDD93611A92B20461c)
