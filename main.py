"""
Triadr - CLI entry point.
Self-Healing Multi-App Agent & Reliability Engine.

    python3 main.py                      # clean run across GitHub + Telegram + Stripe
    python3 main.py --scenario chaos     # same run under a 75%-failure fault storm
    python3 main.py --scenario rollback  # Stripe outage -> full saga compensation
    python3 main.py --scenario rejected  # reviewer rejects -> payout never fires
    python3 main.py --scenario all       # every scenario, with a comparison table
    python3 main.py --bench              # measured gate overhead
    python3 main.py --verify <log.jsonl> # re-verify a previous run's hash chain
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List, Optional

from env import load_env

load_env()

from agents import ReliabilityLogger, TriadrOrchestrator, default_instruction
from mcp_servers import MCPRegistry
from risk_gate import ChaosProfile, FaultType, ReliabilityGate

# Built from the effective defaults, so a LIVE .env shows its real repo,
# channel and connected account here rather than the demo placeholders.
DEFAULT_INSTRUCTION = default_instruction()

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
GREEN, YELLOW, RED, CYAN, MAGENTA = "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[35m"

_STATUS_STYLE = {
    "succeeded": (GREEN, "OK"),
    "healed": (YELLOW, "HEALED"),
    "skipped": (DIM, "SKIP"),
    "failed": (RED, "FAIL"),
    "compensated": (MAGENTA, "UNDONE"),
    "pending": (DIM, "..."),
    "running": (CYAN, "RUN"),
}


def _rule(char: str = "─", width: int = 78) -> str:
    return DIM + char * width + RESET


def _banner() -> None:
    print()
    print(f"{BOLD}  TRIADR{RESET} {DIM}- Self-Healing Multi-App Agent & Reliability Engine{RESET}")
    print(f"  {DIM}App #1 GitHub (audit) · App #2 Telegram (approval) · App #3 Stripe (escrow){RESET}")
    print(_rule())


def _print_apps(registry: MCPRegistry) -> None:
    status = registry.status()
    for app in status["apps"]:
        colour = GREEN if app["mode"] == "LIVE" else CYAN
        missing = f" {DIM}(set {', '.join(app['credentials_missing'])} for live mode){RESET}" if app["credentials_missing"] else ""
        print(f"  {colour}●{RESET} {app['app']:<8} {app['mode']:<10} {app['tools']} tools{missing}")
    print(f"  {DIM}{status['tool_count']} MCP tools registered across {len(status['apps'])} connected apps{RESET}")
    print(_rule())


def _print_steps(result) -> None:
    for step in result.steps:
        colour, label = _STATUS_STYLE.get(step.status, (DIM, step.status.upper()))
        attempts = len(step.outcome.attempts) if step.outcome else 0
        retry = f"{DIM}·{attempts} attempts{RESET}" if attempts > 1 else ""
        print(f"  {colour}{label:<7}{RESET} {step.step.id:<14} {DIM}{step.step.tool:<28}{RESET} "
              f"{step.duration_ms:>7.0f}ms {retry}")
        if step.status in ("healed", "failed") and step.note:
            print(f"          {DIM}{step.note[:96]}{RESET}")
    for comp in result.compensations:
        mark = f"{MAGENTA}UNDO{RESET}" if comp["ok"] else f"{RED}UNDO!{RESET}"
        print(f"  {mark}    {comp['undid']:<14} {DIM}via {comp['tool']}{RESET}")


def _print_reliability(result) -> None:
    m = result.gate["metrics"]
    latency = m["gate_latency"]
    print(_rule())
    print(f"  {BOLD}Reliability{RESET}")
    print(f"    calls {m['total_calls']} over {m['total_attempts']} attempts · "
          f"self-healed {m['self_healed']} · deduped {m['deduped']} · unrecoverable {m['compensated']}")
    if m["faults_by_type"]:
        faults = " ".join(f"{k}×{v}" for k, v in sorted(m["faults_by_type"].items()))
        print(f"    faults absorbed {m['faults_absorbed']}: {DIM}{faults}{RESET}")
    print(f"    gate overhead p50 {latency['p50_us']:.2f} µs · p99 {latency['p99_us']:.2f} µs {DIM}(measured){RESET}")
    print(f"    reliability score {BOLD}{m['reliability_score'] * 100:.1f}%{RESET}")

    att = result.attestation
    tick = f"{GREEN}verified{RESET}" if att["chain_valid"] else f"{RED}BROKEN{RESET}"
    print(f"  {BOLD}Audit chain{RESET}")
    print(f"    {att['entry_count']} entries · sha256 chain {tick} · "
          f"{'signed' if att['signed'] else DIM + 'unsigned (set TRIADR_LOG_KEY)' + RESET}")
    print(f"    merkle root {DIM}{att['merkle_root']}{RESET}")
    print(_rule())
    print(f"  {BOLD}{result.summary}{RESET}")
    print()


def run_scenario(
    name: str,
    instruction: str,
    *,
    quiet: bool = False,
    persist: bool = True,
) -> Any:
    """Execute one named scenario and return its WorkflowResult."""
    chaos: Optional[ChaosProfile] = None
    auto_approve = True
    forced: Optional[tuple] = None
    blurb = ""

    if name == "clean":
        blurb = "all three apps healthy"
    elif name == "chaos":
        chaos = ChaosProfile.storm(seed=7)
        blurb = "~75% of calls fail on first attempt; the gate heals them"
    elif name == "rollback":
        forced = ("stripe.release_escrow", FaultType.SERVER_ERROR)
        blurb = "Stripe is hard-down after the approval card is already posted"
    elif name == "rejected":
        auto_approve = False
        blurb = "the reviewing team rejects the payout"
    else:
        raise SystemExit(f"unknown scenario '{name}' (clean | chaos | rollback | rejected | all)")

    registry = MCPRegistry(auto_approve=auto_approve)
    if forced:
        registry.force_fault(*forced)

    if not quiet:
        print(f"\n{BOLD}  Scenario: {name}{RESET} {DIM}- {blurb}{RESET}")
        print(_rule())
        _print_apps(registry)
        print(f"  {DIM}instruction:{RESET} {instruction}")
        print(_rule())

    orchestrator = TriadrOrchestrator(registry=registry, chaos=chaos, run_id=f"run_{name}_{int(time.time())}")
    result = orchestrator.run(instruction)

    if not quiet:
        _print_steps(result)
        _print_reliability(result)
    if persist:
        paths = orchestrator.persist()
        if not quiet:
            print(f"  {DIM}audit log  {paths['log']}{RESET}")
            print(f"  {DIM}attestation {paths['attestation']}{RESET}\n")
    return result


def run_all(instruction: str) -> None:
    rows: List[Dict[str, Any]] = []
    for name in ("clean", "chaos", "rollback", "rejected"):
        result = run_scenario(name, instruction)
        m = result.gate["metrics"]
        rows.append({
            "scenario": name,
            "outcome": "APPLIED" if result.ok else "ROLLED BACK",
            "steps": f"{sum(1 for s in result.steps if s.status in ('succeeded', 'healed'))}/{len(result.steps)}",
            "faults": m["faults_absorbed"],
            "healed": m["self_healed"],
            "undone": len([c for c in result.compensations if c["ok"]]),
            "chain": "valid" if result.attestation["chain_valid"] else "BROKEN",
            "ms": f"{result.duration_ms:.0f}",
        })

    print(_rule("═"))
    print(f"  {BOLD}Scenario comparison{RESET}")
    print(_rule())
    header = f"  {'scenario':<10} {'outcome':<12} {'steps':<7} {'faults':<7} {'healed':<7} {'undone':<7} {'chain':<7} {'ms':>6}"
    print(BOLD + header + RESET)
    for r in rows:
        print(f"  {r['scenario']:<10} {r['outcome']:<12} {r['steps']:<7} {r['faults']:<7} "
              f"{r['healed']:<7} {r['undone']:<7} {r['chain']:<7} {r['ms']:>6}")
    print(_rule("═"))
    print(f"  {DIM}Every scenario ends fully applied or fully reverted - never half-executed.{RESET}\n")


def run_bench(iterations: int) -> None:
    _banner()
    print(f"  {BOLD}Measured gate overhead{RESET} {DIM}({iterations:,} iterations, this machine){RESET}\n")
    data = ReliabilityGate().benchmark(iterations)
    for phase in ("schema_validation", "full_preflight"):
        p = data[phase]
        print(f"  {phase:<20} p50 {p['p50_us']:>7.3f} µs   p95 {p['p95_us']:>7.3f} µs   "
              f"p99 {p['p99_us']:>7.3f} µs   mean {p['mean_us']:>7.3f} µs")
    print(f"\n  {DIM}schema_validation = the zero-LLM contract check that gates every side effect.{RESET}")
    print(f"  {DIM}full_preflight    = that check plus the response drift fingerprint.{RESET}\n")


def verify_log(path: str) -> None:
    logger, verification = ReliabilityLogger.load(path)
    _banner()
    print(f"  {BOLD}Verifying{RESET} {path}\n")
    print(f"    entries      {verification['entries']}")
    print(f"    chain        {(GREEN + 'VALID' + RESET) if verification['valid'] else (RED + 'BROKEN' + RESET)}")
    print(f"    reason       {verification['reason']}")
    if not verification["valid"]:
        print(f"    broken at    entry #{verification['broken_at']}")
    print(f"    merkle root  {logger.merkle_root()}\n")
    sys.exit(0 if verification["valid"] else 1)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="triadr", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", default="clean",
                        choices=["clean", "chaos", "rollback", "rejected", "all"])
    parser.add_argument("--instruction", default=DEFAULT_INSTRUCTION,
                        help="natural-language instruction for the agent")
    parser.add_argument("--bench", action="store_true", help="measure gate overhead and exit")
    parser.add_argument("--bench-iterations", type=int, default=20_000)
    parser.add_argument("--verify", metavar="LOG", help="re-verify a written .jsonl audit log and exit")
    parser.add_argument("--json", action="store_true", help="emit the run result as JSON")
    parser.add_argument("--no-persist", action="store_true", help="do not write the audit log to disk")
    args = parser.parse_args(argv)

    if args.verify:
        verify_log(args.verify)
    if args.bench:
        run_bench(args.bench_iterations)
        return

    if args.json:
        result = run_scenario(args.scenario if args.scenario != "all" else "clean",
                              args.instruction, quiet=True, persist=not args.no_persist)
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return

    _banner()
    if args.scenario == "all":
        run_all(args.instruction)
    else:
        run_scenario(args.scenario, args.instruction, persist=not args.no_persist)


if __name__ == "__main__":
    main()
