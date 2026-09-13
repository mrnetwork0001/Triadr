"""
Triadr - reliability campaign.

Runs the full 3-app saga N times under a deterministic fault storm and reports
the only numbers that matter for a reliability engine:

  * how many runs ended fully applied vs fully rolled back
  * how many faults were absorbed on the way
  * whether any run left money in an inconsistent state
  * whether every audit chain still verifies

Every figure in README.md and docs/RELIABILITY_BRIEF.md comes from this script.
Re-run it to regenerate them:

    python3 scripts/campaign.py --runs 40
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from env import load_env  # noqa: E402

load_env()

from agents import TriadrOrchestrator  # noqa: E402
from mcp_servers import MCPRegistry  # noqa: E402
from risk_gate import ChaosProfile, ReliabilityGate  # noqa: E402

INSTRUCTION = (
    "Audit PR #42 in mrnetwork/triadr, get sign-off in #eng-approvals, "
    "then release $2,500.00 USD from escrow to acct_1TriadrContractor"
)


def campaign(runs: int, quiet: bool = False) -> dict:
    totals = {
        "runs": runs, "applied": 0, "rolled_back": 0, "faults_absorbed": 0,
        "steps_self_healed": 0, "compensations": 0, "chain_valid": 0,
        "inconsistent_money": 0, "duplicate_payouts": 0, "wall_ms": 0.0,
    }
    started = time.perf_counter()

    for seed in range(runs):
        registry = MCPRegistry()
        result = TriadrOrchestrator(
            registry=registry, chaos=ChaosProfile.storm(seed=seed)
        ).run(INSTRUCTION)

        metrics = result.gate["metrics"]
        totals["faults_absorbed"] += metrics["faults_absorbed"]
        totals["steps_self_healed"] += metrics["self_healed"]
        totals["compensations"] += len([c for c in result.compensations if c["ok"]])
        totals["chain_valid"] += int(result.attestation["chain_valid"])

        settled = [t for t in registry.stripe._transfers.values() if not t["reversed"]]
        if len(settled) > 1:
            totals["duplicate_payouts"] += 1
            totals["inconsistent_money"] += 1
        elif not result.ok and settled:
            # A rolled-back run that still moved money is the exact failure mode
            # Triadr exists to prevent.
            totals["inconsistent_money"] += 1

        totals["applied" if result.ok else "rolled_back"] += 1

        if not quiet:
            mark = "applied    " if result.ok else "rolled back"
            print(f"  seed {seed:>3}  {mark}  faults={metrics['faults_absorbed']:>3}  "
                  f"healed={metrics['self_healed']}  undone={len(result.compensations)}  "
                  f"chain={'ok' if result.attestation['chain_valid'] else 'BROKEN'}")

    totals["wall_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=40)
    parser.add_argument("--bench-iterations", type=int, default=50_000)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not args.quiet and not args.json:
        print(f"\nTriadr reliability campaign - {args.runs} runs under a ~75% fault storm\n")

    totals = campaign(args.runs, quiet=args.quiet or args.json)
    bench = ReliabilityGate().benchmark(args.bench_iterations)

    if args.json:
        print(json.dumps({"campaign": totals, "benchmark": bench}, indent=2))
        return

    print("\n" + "─" * 72)
    print(f"  runs                     {totals['runs']}")
    print(f"  fully applied            {totals['applied']}")
    print(f"  fully rolled back        {totals['rolled_back']}")
    print(f"  faults absorbed          {totals['faults_absorbed']}")
    print(f"  steps self-healed        {totals['steps_self_healed']}")
    print(f"  side effects reverted    {totals['compensations']}")
    print(f"  audit chains valid       {totals['chain_valid']}/{totals['runs']}")
    print(f"  duplicate payouts        {totals['duplicate_payouts']}")
    print(f"  inconsistent money       {totals['inconsistent_money']}")
    print(f"  wall clock               {totals['wall_ms']:.0f} ms")
    print("─" * 72)
    print(f"  gate overhead - schema validation  p50 {bench['schema_validation']['p50_us']:.3f} µs  "
          f"p99 {bench['schema_validation']['p99_us']:.3f} µs")
    print(f"  gate overhead - full pre-flight    p50 {bench['full_preflight']['p50_us']:.3f} µs  "
          f"p99 {bench['full_preflight']['p99_us']:.3f} µs")
    print("─" * 72)
    verdict = "PASS" if totals["inconsistent_money"] == 0 and totals["chain_valid"] == totals["runs"] else "FAIL"
    print(f"  invariant - no run left money inconsistent, every chain verifies: {verdict}\n")
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
