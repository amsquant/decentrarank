# DecentraRank Universal Schema Specification

> Version 0.1 — May 2026
> Status: Draft for grant submission

## Overview

The DecentraRank Universal Schema is a domain-agnostic data model for ranking
and indexing entities on the 0G Network. Any ranked entity — a validator, a
DeFi pool, an AI inference provider, a research dataset, an in-game asset —
can be represented in this schema and consumed by the universal ranking engine.

The schema is **intentionally minimal at its core** and **extensible at its edges**.
Five signals are universal across all domains. Domain-specific adapters extend
these with vertical-relevant metadata without modifying the core.

## Core principles

1. **Universality over specificity.** The core schema must apply to any rankable entity. Specifics live in domain extensions.
2. **Stable identifiers.** Every entity has a deterministic, content-addressable identifier persisted on 0G Storage.
3. **Provenance is first-class.** Every record carries the on-chain proof of who produced it and when.
4. **Append-only.** Records are immutable; updates are new records linked to predecessors.
5. **Composable.** A ranked output from one DecentraRank index can become an input to another.

## Core schema

```python
@dataclass
class Entity:
    """The canonical ranked entity, domain-agnostic."""

    # Identity
    entity_id:      str               # content-addressable hash (CID)
    entity_type:    str               # e.g. "validator", "defi_pool"
    domain:         str               # adapter namespace, e.g. "0g.staking"

    # Universal signals — every entity must populate these
    relevance:      float             # 0.0 to 1.0; query-context match
    recency:        float             # 0.0 to 1.0; freshness-decay weighted
    provenance:     float             # 0.0 to 1.0; producer reputation
    reliability:    float             # 0.0 to 1.0; historical accuracy
    cost:           float             # 0.0 to 1.0; lower cost = higher score

    # Provenance metadata
    producer:       str               # on-chain producer address
    submitted_at:   int               # block number of first record
    last_updated:   int               # block number of latest update

    # Domain extension envelope
    extensions:     dict              # adapter-specific structured metadata

    # Composite ranking (computed, not submitted)
    composite_score: Optional[float] = None
```

## The five universal signals

### 1. Relevance — `0.0` to `1.0`

How well does this entity match the query context? Relevance is the most
context-dependent signal and is computed at query time, not indexing time.

For validators: relevance might score how well the validator's profile matches
a delegator's stated preferences (high-uptime focused, low-commission focused,
geographically diverse, etc).

### 2. Recency — `0.0` to `1.0`

How fresh is the data, weighted by domain-appropriate decay rates?

| Domain | Recency window |
|---|---|
| Validators | Last 1,000 blocks (~1 hour) |
| DeFi pools | Last 24 hours |
| AI inference | Last 6 hours |
| Research datasets | Last 30 days |

The decay function is exponential with a half-life set per domain.

### 3. Provenance — `0.0` to `1.0`

Who produced this data, and what is their on-chain reputation? Provenance
score is itself a ranking — a recursive application of DecentraRank to the
producers themselves.

For validators: provenance is the validator's identity transparency, KYC
status, infrastructure disclosure, and historical conduct.

### 4. Reliability — `0.0` to `1.0`

Historical accuracy, completion rate, and consistency. The most domain-stable
signal — the same definition applies almost everywhere.

For validators: combined uptime % and missed-block rate.

### 5. Cost — `0.0` to `1.0`

What is the economic cost of consuming this entity, normalised across domains?
Lower cost yields a higher score (i.e., this is `1 - normalised_cost`).

For validators: 1 minus normalised commission rate.

## Composite scoring

The composite ranking score is a weighted linear combination of the five
universal signals:

```
composite = w_rel * relevance
          + w_rec * recency
          + w_pro * provenance
          + w_rel2 * reliability
          + w_cost * cost
```

where the weights `w_*` sum to 1.0 and are calibrated per-domain through the
MABS calibration loop. The default reference weights are:

| Signal | Default weight |
|---|---|
| Relevance | 0.20 |
| Recency | 0.15 |
| Provenance | 0.20 |
| Reliability | 0.30 |
| Cost | 0.15 |

These defaults are intentionally biased toward reliability, on the principle
that consumers of any ranking generally value *trustworthiness* above other
factors. Domain-specific MABS calibration tunes these weights based on
observed agent behaviour.

## Domain extensions

The `extensions` field on each entity carries domain-specific structured
metadata. Extensions are namespaced by domain. Example for a validator:

```json
{
  "extensions": {
    "0g.staking": {
      "moniker": "ExampleValidator",
      "operator_address": "0xaED4...",
      "commission_rate": 0.05,
      "delegations_total": "500000000000000000000000",
      "self_bond":         "100000000000000000000000",
      "uptime_percent":     99.94,
      "blocks_signed":      127450,
      "blocks_proposed":    1840,
      "slashing_events":    [],
      "jailed":             false
    }
  }
}
```

Extensions are validated against per-domain JSON schemas published alongside
each adapter. Extensions never affect the core composite score directly; they
inform the universal signal calculations through adapter-specific logic.

## Storage on 0G

Entities are serialised as canonical JSON, hashed to produce the `entity_id`,
and persisted on 0G Storage with the hash as the content address. The 0G DA
layer ensures that the index is verifiable. Updates produce new records that
link to predecessors via `previous_entity_id`, forming an append-only history.

## Query interface

The query API exposes:

- `GET /index/:domain` — list ranked entities in a domain
- `GET /entity/:entity_id` — fetch a single entity with full history
- `POST /query` — structured query with filters and custom weight overrides
- `GET /health` — index freshness, last update block, schema version

A reference REST + GraphQL implementation will be released in Milestone 3 of
the grant.

## Versioning

Schema versions are semantic (`MAJOR.MINOR.PATCH`). Breaking changes increment
`MAJOR`. Adapters declare the schema version they target; the ranking engine
supports the current and previous `MAJOR` versions.

This document specifies version `0.1`. Stable `1.0` will be locked at the end
of grant Milestone 1 (Months 1–2).
