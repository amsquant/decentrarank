#!/usr/bin/env python3
"""
run_simulation.py — DecentraRank MABS simulation + weight calibration.

Runs a full simulation against the validator dataset, then runs the
calibration sweep to derive optimal universal-signal weights from
emergent agent behaviour.

Outputs:
  - Convergence chart (PNG)
  - Calibration heatmap (PNG)
  - Full simulation log (JSON)

Usage:
  python scripts/run_simulation.py [--replay] [--steps 100] [--no-calibrate]
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decentrarank.ingestion.pipeline import run_ingestion
from decentrarank.mabs.simulation import (
    SimulationConfig,
    run_simulation,
    scenario_from_validators,
)
from decentrarank.mabs.calibration import calibrate, evaluate_candidate
from decentrarank.schema import DEFAULT_WEIGHTS


def render_charts(result, calibration, output_dir: Path) -> None:
    """Generate the convergence chart and calibration heatmap."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("[charts] matplotlib not installed — skipping. pip install matplotlib")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Convergence chart ──────────────────────────────────────────────────
    steps = [log.step for log in result.step_logs]
    producer_names = [p.name for p in result.producers]

    # Build score history: producer → list of scores (one per step)
    history = {n: [] for n in producer_names}
    for log in result.step_logs:
        score_map = dict(log.rankings)
        for n in producer_names:
            history[n].append(score_map.get(n, 0.0))

    # Plot only top N at the end, plus the PI's validator if present
    final_top = [n for n, _ in result.step_logs[-1].rankings[:6]]
    if "DecentraRank-Validator" not in final_top:
        final_top.append("DecentraRank-Validator")

    fig, axes = plt.subplots(2, 1, figsize=(11, 8.5))
    fig.patch.set_facecolor("#FAFBFE")
    palette = ["#1B5299", "#3A86FF", "#0A7E6E", "#E07A5F", "#8b5cf6", "#BA7517", "#C0392B"]

    # Top panel: composite score over time
    ax1 = axes[0]; ax1.set_facecolor("#FAFBFE")
    for i, n in enumerate(final_top):
        scores = history.get(n, [])
        if not scores: continue
        ax1.plot(steps, scores, label=n, linewidth=2, color=palette[i % len(palette)])
    ax1.set_title("MABS — Composite ranking score over time", fontsize=13, fontweight="bold", pad=10)
    ax1.set_ylabel("Composite score", fontsize=11)
    ax1.set_ylim(0, 1.0)
    ax1.legend(loc="lower right", fontsize=8, ncol=2)
    ax1.grid(True, alpha=0.3, linestyle="--")
    ax1.spines[["top", "right"]].set_visible(False)

    # Bottom panel: rank position over time
    ax2 = axes[1]; ax2.set_facecolor("#FAFBFE")
    for i, n in enumerate(final_top):
        rank_history = []
        for log in result.step_logs:
            ranks = [name for name, _ in log.rankings]
            try:
                rank_history.append(ranks.index(n) + 1)
            except ValueError:
                rank_history.append(len(ranks))
        ax2.plot(steps, rank_history, label=n, linewidth=2, color=palette[i % len(palette)])
    ax2.set_title("MABS — Rank position over time (1 = top-ranked)", fontsize=13, fontweight="bold", pad=10)
    ax2.set_ylabel("Rank position", fontsize=11)
    ax2.set_xlabel("Simulation step", fontsize=11)
    ax2.set_ylim(len(producer_names) + 0.5, 0.5)
    ax2.legend(loc="upper right", fontsize=8, ncol=2)
    ax2.grid(True, alpha=0.3, linestyle="--")
    ax2.spines[["top", "right"]].set_visible(False)

    # Annotate convergence
    cstep = result.convergence_step()
    if cstep:
        for ax in axes:
            ax.axvline(x=cstep, color="#888", linestyle=":", linewidth=1.5)
            ax.text(cstep + 0.5, ax.get_ylim()[1] * 0.95 if ax is ax1 else ax.get_ylim()[0] * 0.95,
                    f"Top-1 stable at step {cstep}", fontsize=9, color="#555")

    plt.tight_layout(pad=2.0)
    plt.savefig(output_dir / "mabs_convergence.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[charts] mabs_convergence.png written")

    # ── Calibration result chart ───────────────────────────────────────────
    if calibration is None:
        return

    fig2, ax3 = plt.subplots(figsize=(11, 7))
    fig2.patch.set_facecolor("#FAFBFE")
    ax3.set_facecolor("#FAFBFE")

    # Show top 6 + bottom 6 so we can see the full spread of the calibration
    # search space, not just the saturated top.
    full_history = sorted(calibration.search_history, key=lambda t: t[1], reverse=True)
    top_n = 6
    show = full_history[:top_n] + [(None, None)] + full_history[-top_n:]

    labels: List[str] = []
    scores: List[float] = []
    colors: List[str] = []
    for entry in show:
        if entry == (None, None):
            labels.append("…")
            scores.append(0.0)
            colors.append("#FFFFFF00")  # invisible
            continue
        w, s = entry
        labels.append(
            f"R={w['reliability']:.1f}  C={w['cost']:.1f}  "
            f"P={w['provenance']:.1f}  Rec={w['recency']:.1f}  Rel={w['relevance']:.1f}"
        )
        scores.append(s)
        colors.append("#3A86FF")

    bars = ax3.barh(range(len(labels)), scores, color=colors,
                    edgecolor="white", linewidth=1)
    ax3.set_yticks(range(len(labels)))
    ax3.set_yticklabels(labels, fontsize=8.5, family="monospace")
    ax3.invert_yaxis()
    ax3.set_xlabel("Calibration objective score (higher = better)", fontsize=10)
    ax3.set_title("MABS Calibration — top 6 vs bottom 6 weight candidates",
                  fontsize=12, fontweight="bold", pad=12)
    ax3.set_xlim(0, 1.05)
    ax3.grid(True, axis="x", alpha=0.3, linestyle="--")
    ax3.spines[["top", "right"]].set_visible(False)

    # Highlight the best
    if bars:
        bars[0].set_color("#0A7E6E")

    # Add value labels
    for bar, score, color in zip(bars, scores, colors):
        if color == "#FFFFFF00":
            continue
        ax3.text(score + 0.01, bar.get_y() + bar.get_height() / 2,
                 f"{score:.4f}", va="center", fontsize=8.5, color="#333")

    # Annotation
    spread = full_history[0][1] - full_history[-1][1]
    ax3.text(0.5, len(labels) - 0.3,
             f"Score spread across full search: {spread:.3f}  "
             f"(higher spread → calibration matters more)",
             fontsize=9, color="#666", ha="center", style="italic")

    plt.tight_layout()
    plt.savefig(output_dir / "mabs_calibration.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[charts] mabs_calibration.png written")


def main() -> int:
    parser = argparse.ArgumentParser(description="DecentraRank MABS simulation + calibration")
    parser.add_argument("--rpc-endpoint",  help="0G JSON-RPC endpoint (or env)")
    parser.add_argument("--rest-endpoint", help="0G Tendermint REST endpoint (or env)")
    parser.add_argument("--replay", action="store_true", help="Use replay snapshot instead of live RPC")
    parser.add_argument("--steps",  type=int, default=100, help="Number of simulation steps")
    parser.add_argument("--no-calibrate", action="store_true", help="Skip the calibration sweep")
    parser.add_argument("--output-dir", default="build", help="Where to write outputs")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("\nDecentraRank MABS — Simulation + Calibration")
    print("=" * 72)

    # Step 1: ingestion
    ingestion = run_ingestion(
        rpc_endpoint  = args.rpc_endpoint,
        rest_endpoint = args.rest_endpoint,
        force_replay  = args.replay,
    )
    print(f"  Validators ingested : {len(ingestion.entities)} (source: {ingestion.source})")

    # Step 2: build scenario
    config = SimulationConfig(n_steps=args.steps)
    producers, consumers, observer = scenario_from_validators(ingestion.entities, seed=config.seed)
    n_adv = sum(1 for p in producers if p.is_adversarial)
    print(f"  Simulation scenario : {len(producers)} producers ({n_adv} adversarial), "
          f"{len(consumers)} consumers, 1 observer")

    # Step 3: run simulation under default weights
    print(f"  Running simulation  : {config.n_steps} steps × {config.requests_per_step} requests/step")
    result = run_simulation(producers, consumers, observer, config)
    cstep = result.convergence_step()
    print(f"  Convergence         : top-1 stable from step {cstep}" if cstep else
          "  Convergence         : top-1 not fully converged")

    # Step 4: calibration
    calibration = None
    if not args.no_calibrate:
        print(f"  Running calibration : weight grid sweep")
        calibration = calibrate(ingestion.entities, grid_step=0.10, config=config)
        print(f"  Best weights        : {calibration.best_weights}")
        print(f"  Best objective      : {calibration.best_score:.4f}")
        print(f"  vs default weights  : ", end="")
        default_score, _ = evaluate_candidate(DEFAULT_WEIGHTS, ingestion.entities, config=config)
        print(f"{default_score:.4f} (default)  → {calibration.best_score:.4f} (calibrated)")

    # Step 5: render charts + write logs
    output_dir = Path(args.output_dir)
    render_charts(result, calibration, output_dir)

    # Final rankings table
    print("\nFinal rankings (after calibration):")
    print("-" * 56)
    for i, (name, score) in enumerate(result.final_rankings()[:10], 1):
        marker = ["[1]", "[2]", "[3]"][i-1] if i <= 3 else f"  {i:>2}."
        producer = next((p for p in producers if p.name == name), None)
        if producer is None:
            continue
        n_received = producer.selections_received
        n_success  = producer.successful_outcomes
        adv_flag   = " (!)" if producer.is_adversarial else ""
        flagged    = f" [F:{producer.detected_misbehaviours}]" if producer.detected_misbehaviours else ""
        print(f"  {marker} {name + adv_flag + flagged:<32} score={score:.4f}  "
              f"selected={n_received:>4}  successes={n_success:>4}")
    print()

    # Step 6: persist JSON log
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "mabs_simulation_log.json"
    log_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "n_steps":           config.n_steps,
            "requests_per_step": config.requests_per_step,
            "seed":              config.seed,
        },
        "ingestion_source": ingestion.source,
        "n_producers":  len(producers),
        "n_consumers":  len(consumers),
        "convergence_step": cstep,
        "final_rankings": result.final_rankings(),
        "flagged_history": observer.flagged_history,
        "calibration": ({
            "best_weights":   calibration.best_weights,
            "best_score":     calibration.best_score,
            "search_history": [
                {"weights": w, "score": s}
                for w, s in calibration.search_history
            ],
        } if calibration else None),
    }
    log_path.write_text(json.dumps(log_payload, indent=2))
    print(f"  Simulation log written to: {log_path.resolve()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
