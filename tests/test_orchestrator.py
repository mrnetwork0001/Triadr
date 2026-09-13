"""Tests for the saga orchestrator - the all-or-nothing guarantee lives here."""

import pytest

from agents import TriadrOrchestrator, plan_from_instruction
from agents.orchestrator import StepStatus
from mcp_servers import MCPRegistry
from risk_gate import ChaosProfile, FaultType

INSTRUCTION = (
    "Audit PR #42 in mrnetwork/triadr, get sign-off in #eng-approvals, "
    "then release $2,500.00 USD from escrow to acct_1TriadrContractor"
)


def orchestrator(**kwargs) -> TriadrOrchestrator:
    kwargs.setdefault("registry", MCPRegistry(auto_approve=kwargs.pop("auto_approve", True)))
    return TriadrOrchestrator(**kwargs)


class TestPlanner:
    def test_extracts_every_parameter_from_free_text(self):
        params = plan_from_instruction(INSTRUCTION).params
        assert params["repo"] == "mrnetwork/triadr"
        assert params["pr_number"] == 42
        assert params["chat_id"] == "@triadr_approvals"
        assert params["amount"] == 2500.0
        assert params["contractor"] == "acct_1TriadrContractor"

    def test_a_pr_number_is_never_read_as_a_channel(self):
        assert plan_from_instruction("look at PR #77 please").params["chat_id"] == "@triadr_approvals"

    def test_a_pr_number_is_never_read_as_an_amount(self):
        assert plan_from_instruction("audit PR #999").params["amount"] == 2500.0

    def test_currency_follows_the_instruction(self):
        params = plan_from_instruction("pay EUR 1,200.50 to acct_9ZZ for PR #3").params
        assert params["currency"] == "eur" and params["amount"] == 1200.50

    def test_the_plan_shape_is_fixed_and_spans_all_three_apps(self):
        plan = plan_from_instruction("do something vague")
        assert [s.id for s in plan.steps] == [
            "audit", "status", "approval_card", "approval", "payout", "receipt"
        ]
        assert sorted({s.app for s in plan.steps}) == ["github", "stripe", "telegram"]

    def test_the_payout_is_conditional_on_approval(self):
        payout = next(s for s in plan_from_instruction(INSTRUCTION).steps if s.id == "payout")
        assert payout.condition == "approval.decision == approved"
        assert payout.idempotency_key and payout.compensation

    def test_the_idempotency_key_is_derived_from_the_workload(self):
        a = plan_from_instruction(INSTRUCTION, run_id="run-a")
        b = plan_from_instruction(INSTRUCTION, run_id="run-b")
        key = lambda p: next(s for s in p.steps if s.id == "payout").idempotency_key
        assert key(a) == key(b), "re-running the same payout must collapse onto one key"

    def test_a_different_amount_produces_a_different_key(self):
        key = lambda text: next(s for s in plan_from_instruction(text).steps if s.id == "payout").idempotency_key
        assert key(INSTRUCTION) != key(INSTRUCTION.replace("$2,500.00", "$3,000.00"))


class TestTemplating:
    def test_a_lone_reference_keeps_its_native_type(self):
        o = orchestrator()
        assert o._resolve("${audit}", {"audit": {"a": 1}}) == {"a": 1}

    def test_an_embedded_reference_interpolates_as_text(self):
        o = orchestrator()
        assert o._resolve("risk ${a.score}/100", {"a": {"score": 88}}) == "risk 88/100"

    def test_nested_structures_are_resolved(self):
        o = orchestrator()
        assert o._resolve({"x": ["${a.b}"]}, {"a": {"b": 5}}) == {"x": [5]}

    @pytest.mark.parametrize(
        "condition, context, expected",
        [
            ("approval.decision == approved", {"approval": {"decision": "approved"}}, True),
            ("approval.decision == approved", {"approval": {"decision": "rejected"}}, False),
            ("audit.auto_mergeable", {"audit": {"auto_mergeable": True}}, True),
            ("audit.auto_mergeable", {"audit": {"auto_mergeable": False}}, False),
            (None, {}, True),
        ],
    )
    def test_conditions(self, condition, context, expected):
        assert TriadrOrchestrator._condition_met(condition, context) is expected


class TestHappyPath:
    def test_all_six_steps_apply_across_three_apps(self):
        result = orchestrator().run(INSTRUCTION)
        assert result.ok
        assert all(s.status == StepStatus.SUCCEEDED for s in result.steps)
        assert result.attestation["chain_valid"]
        assert result.attestation["outcome"] == "APPLIED"

    def test_the_payout_actually_settles(self):
        result = orchestrator().run(INSTRUCTION)
        payout = next(s for s in result.steps if s.step.id == "payout")
        assert payout.output["status"] == "paid"
        assert payout.output["amount"] == 250_000  # cents

    def test_every_step_is_recorded_in_the_audit_chain(self):
        o = orchestrator()
        result = o.run(INSTRUCTION)
        kinds = result.attestation["entry_kinds"]
        assert kinds["run.start"] == 1 and kinds["run.end"] == 1
        assert kinds["gate.outcome"] >= len(result.steps)


class TestChaos:
    """The guarantee under chaos is not "the payout always happens" - a real
    outage can be unrecoverable. The guarantee is that the run ends fully applied
    or fully reverted, and that money never moves more than once."""

    SEEDS = [3, 7, 11, 13, 21, 42, 99, 137]

    @pytest.mark.parametrize("seed", SEEDS)
    def test_the_saga_is_never_left_half_executed(self, seed):
        registry = MCPRegistry()
        result = TriadrOrchestrator(registry=registry, chaos=ChaosProfile.storm(seed=seed)).run(INSTRUCTION)

        assert result.attestation["chain_valid"], "the audit chain must survive any fault pattern"
        assert result.attestation["outcome"] in ("APPLIED", "ROLLED_BACK")

        settled = [t for t in registry.stripe._transfers.values() if not t["reversed"]]
        if result.ok:
            payout = next((s for s in result.steps if s.step.id == "payout"), None)
            assert payout is not None
            if payout.status in (StepStatus.SUCCEEDED, StepStatus.HEALED):
                assert len(settled) == 1, "an applied run settles exactly one transfer"
        else:
            assert settled == [], "a rolled-back run must leave no money moved"
            # Every side effect that was applied before the failure must be undone.
            applied = [s for s in result.steps if s.step.compensation
                       and s.status in (StepStatus.SUCCEEDED, StepStatus.HEALED)]
            assert applied == [], f"un-reverted side effects remain: {[s.step.id for s in applied]}"

    def test_faults_are_actually_being_injected(self):
        result = orchestrator(chaos=ChaosProfile.storm(seed=11)).run(INSTRUCTION)
        assert result.gate["metrics"]["faults_absorbed"] > 0, "the storm must actually storm"

    def test_chaos_never_pays_twice(self):
        registry = MCPRegistry()
        TriadrOrchestrator(registry=registry, chaos=ChaosProfile.storm(seed=13)).run(INSTRUCTION)
        assert len(registry.stripe._transfers) <= 1


class TestRejection:
    def test_a_rejected_approval_skips_the_payout(self):
        registry = MCPRegistry(auto_approve=False)
        result = TriadrOrchestrator(registry=registry).run(INSTRUCTION)
        payout = next(s for s in result.steps if s.step.id == "payout")
        assert payout.status == StepStatus.SKIPPED
        assert registry.stripe._transfers == {}, "a rejected review must move no money"

    def test_the_receipt_is_skipped_when_the_payout_is(self):
        result = TriadrOrchestrator(registry=MCPRegistry(auto_approve=False)).run(INSTRUCTION)
        receipt = next(s for s in result.steps if s.step.id == "receipt")
        assert receipt.status == StepStatus.SKIPPED


class TestRollback:
    @pytest.fixture
    def rolled_back(self):
        registry = MCPRegistry()
        registry.force_fault("stripe.release_escrow", FaultType.SERVER_ERROR)
        return registry, TriadrOrchestrator(registry=registry).run(INSTRUCTION)

    def test_the_run_is_marked_rolled_back(self, rolled_back):
        _, result = rolled_back
        assert not result.ok
        assert result.attestation["outcome"] == "ROLLED_BACK"

    def test_every_applied_side_effect_is_undone(self, rolled_back):
        _, result = rolled_back
        assert {c["undid"] for c in result.compensations} == {"approval_card", "status"}
        assert all(c["ok"] for c in result.compensations)

    def test_compensations_run_in_reverse_order(self, rolled_back):
        _, result = rolled_back
        assert [c["undid"] for c in result.compensations] == ["approval_card", "status"]

    def test_no_money_moved(self, rolled_back):
        registry, _ = rolled_back
        assert registry.stripe._transfers == {}

    def test_the_chain_still_verifies_after_a_rollback(self, rolled_back):
        _, result = rolled_back
        assert result.attestation["chain_valid"]


class TestNonCriticalSteps:
    def test_a_failed_receipt_does_not_reverse_a_settled_payout(self):
        registry = MCPRegistry()
        registry.force_fault("telegram.post_message", FaultType.SERVER_ERROR)
        result = TriadrOrchestrator(registry=registry).run(INSTRUCTION)
        assert result.ok, "a cosmetic step must not undo a completed payment"
        assert result.compensations == []
        assert len(registry.stripe._transfers) == 1


class TestEventStream:
    def test_the_dashboard_receives_a_full_lifecycle(self):
        events = []
        registry = MCPRegistry()
        TriadrOrchestrator(registry=registry, on_event=events.append).run(INSTRUCTION)
        names = {e["event"] for e in events}
        assert {"run.start", "step.start", "step.done", "run.end"} <= names

    def test_a_broken_listener_never_breaks_the_run(self):
        def explode(_event):
            raise RuntimeError("dashboard died")

        result = TriadrOrchestrator(registry=MCPRegistry(), on_event=explode).run(INSTRUCTION)
        assert result.ok


class TestHonestRollbackSummary:
    """A rollback that did not fully succeed must not be reported as clean."""

    def test_incomplete_rollback_is_reported_as_incomplete(self):
        o = TriadrOrchestrator(registry=MCPRegistry())
        summary = o._summarise(
            ok=False,
            results=[],
            compensations=[{"undid": "a", "tool": "t.undo", "ok": True},
                           {"undid": "b", "tool": "t.undo", "ok": False}],
            context={},
        )
        assert "INCOMPLETE" in summary and "1 could not be undone" in summary
        assert "No partial state remains" not in summary, "a failed reversal must never claim cleanliness"

    def test_complete_rollback_still_reads_clean(self):
        o = TriadrOrchestrator(registry=MCPRegistry())
        summary = o._summarise(
            ok=False,
            results=[],
            compensations=[{"undid": "a", "tool": "t.undo", "ok": True}],
            context={},
        )
        assert "rolled back cleanly" in summary and "No partial state remains" in summary


class TestPayoutPayloadMatchesItsKey:
    """Stripe rejects a reused idempotency key whose parameters changed, so the
    payout payload must not vary between runs of the same workload."""

    def test_payout_args_are_identical_across_runs(self):
        a = plan_from_instruction(INSTRUCTION, run_id="run-a")
        b = plan_from_instruction(INSTRUCTION, run_id="run-b")
        payout = lambda p: next(s for s in p.steps if s.id == "payout")
        assert payout(a).idempotency_key == payout(b).idempotency_key
        assert payout(a).args == payout(b).args, (
            "same key, different parameters - Stripe would answer 400 on the second run"
        )

    def test_run_id_is_not_in_the_payment_payload(self):
        payout = next(s for s in plan_from_instruction(INSTRUCTION, run_id="run-xyz").steps if s.id == "payout")
        assert "run-xyz" not in str(payout.args)
