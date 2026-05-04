# Index Decision: Why Validator Ranking

> Decision rationale for the DecentraRank prototype's first indexing target.
> This document justifies the choice and is referenced in the grant proposal.

## Decision

**The DecentraRank prototype will index and rank the active validator set on the 0G Aristotle mainnet.**

The universal schema and ranking engine remain domain-agnostic — validator ranking is the first vertical adapter, chosen because it provides the strongest demonstration of the full DecentraRank stack against real, in-volume, on-chain data.

## Rationale

### 1. Real, in-volume, indexable data

The 0G Aristotle mainnet (launched September 2025) currently maintains an active validator set of approximately 54 validators with stake delegated across them. This is a small but operationally meaningful dataset — every validator produces a continuous stream of:

- Block signing / proposal records
- Stake delegations and undelegations
- Commission rate adjustments
- Uptime and missed-block events
- Slashing events (rare but high-signal)

This is the kind of data that exists *today*, in volume sufficient to demonstrate ranking, but bounded enough to be fully analysable by a small team.

### 2. The Principal Investigator is part of the dataset

The PI operates an active 0G validator (`0xaED4832042D1204Faf7a97eDD93611A92B20461c`). This means:

- The team has direct, unmediated access to the data being indexed
- The team understands the operational reality of validators — what makes one good or bad
- The demo includes the team's own validator alongside its peers, enabling honest, transparent benchmarking

This is a level of authentic engagement that no purely external indexing project can match.

### 3. Universal schema fits naturally

DecentraRank's five universal signals map directly onto validator metrics, validating the schema design:

| Universal Signal | Validator Mapping |
|---|---|
| **Reliability** | Uptime %, blocks signed / blocks expected, slashing history |
| **Cost** | Commission rate, minimum self-bond |
| **Provenance** | Validator identity, KYC status, jurisdiction, infrastructure transparency |
| **Recency** | Recent (last 100 blocks) performance vs. lifetime average |
| **Relevance** | Match against the consumer's stake size, risk tolerance, and decentralisation preference |

If the schema works for validators, the same design works for any other ranked entity.

### 4. Multi-Agent Based Simulation fits cleanly

The validator-delegator market is a textbook MABS scenario:

- **Producer agents** = validators competing for delegations
- **Consumer agents** = delegators with diverse preferences, stake sizes, and risk profiles
- **Validator-of-validators agents** = network observers monitoring producer misbehaviour

Agent interactions produce observable, calibrate-able dynamics: stake flows, commission wars, reputation effects.

### 5. Real ecosystem need

Every 0G token holder choosing where to delegate faces a multi-criteria optimisation problem with imperfect information. Today they typically pick the validator with the highest visibility or the lowest commission, ignoring reliability and decentralisation. DecentraRank solves a real problem that 0G stakeholders — including, very plausibly, Guild on 0G grant reviewers — actually face.

### 6. Generalisation path is clear

After validating the architecture against validator data, the same code paths extend to:

- DeSci research datasets (provenance and citation quality)
- DeFi protocols and liquidity pools (TVL, slippage, security history)
- AI agents and inference providers (latency, accuracy, cost)
- iNFTs and content (engagement, originality, creator reputation)

The validator vertical is the sharpest knife edge for proving the architecture; everything else is a domain adapter on top.

## Alternatives considered and rejected

| Alternative | Reason rejected |
|---|---|
| AI inference task events on 0G Compute | 0G Compute mainnet is still in late-2025/2026 rollout; data volume too sparse for a credible demo |
| Token transfer / wallet activity | Privacy concerns; ranking signal is weak; doesn't differentiate from generic block explorers |
| Smart contract deployments | Too few contracts deployed to date for meaningful ranking |
| .0G domain registrations | Newer feature; insufficient data; weak universality story |
| Synthetic data only | Would undermine the proposal's claim of live RPC integration |

## Implementation status

- **Implemented:** RPC client connecting to 0G mainnet, validator-set adapter, normaliser to canonical schema, scoring engine across all five universal signals.
- **Implemented:** Three-agent MABS simulation calibrated against the produced validator dataset.
- **Pending production deployment:** Continuous live indexing daemon, public query API, formal third-party security audit.
