"""Tests for the reliability gate - the claims Triadr makes must be enforced here."""

import pytest

from risk_gate import (
    BackoffPolicy, ChaosEngine, ChaosProfile, CircuitBreaker, CircuitState, DriftDetector,
    EndpointRouter, FaultType, IdempotencyLedger, ReliabilityGate, SchemaValidator, TokenBucket,
    ToolFault, Verdict,
)

PAYOUT_SCHEMA = {
    "type": "object",
    "required": ["action", "amount", "currency"],
    "properties": {
        "action": {"type": "string", "const": "release_escrow"},
        "amount": {"type": "number", "exclusiveMinimum": 0, "maximum": 1_000_000},
        "currency": {"type": "string", "format": "currency-code"},
    },
    "additionalProperties": False,
}
VALID = {"action": "release_escrow", "amount": 2500.0, "currency": "usd"}


def gate(**kwargs) -> ReliabilityGate:
    kwargs.setdefault("sleep", lambda _s: None)  # never sleep in tests
    return ReliabilityGate(**kwargs)


def ok_executor(*, payload, endpoint):
    return {"id": "tr_1", "amount": payload["amount"], "currency": payload["currency"], "status": "paid"}


# --------------------------------------------------------------------------
# Schema validation
# --------------------------------------------------------------------------


class TestSchemaValidator:
    def test_accepts_a_valid_payload(self):
        assert SchemaValidator(PAYOUT_SCHEMA).is_valid(VALID)

    @pytest.mark.parametrize(
        "payload, rule",
        [
            ({"amount": 1.0, "currency": "usd"}, "required"),
            ({**VALID, "amount": -1}, "exclusiveMinimum"),
            ({**VALID, "amount": 2_000_000}, "maximum"),
            ({**VALID, "currency": "US-DOLLAR"}, "format"),
            ({**VALID, "action": "delete_everything"}, "const"),
            ({**VALID, "extra": True}, "additionalProperties"),
            ({**VALID, "amount": "2500"}, "type"),
        ],
    )
    def test_rejects_bad_payloads(self, payload, rule):
        violations = SchemaValidator(PAYOUT_SCHEMA).validate(payload)
        assert any(v.rule == rule for v in violations), violations

    def test_bool_is_not_an_integer(self):
        schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
        assert SchemaValidator(schema).validate({"n": True})

    def test_nested_and_array_paths_are_reported(self):
        schema = {
            "type": "object",
            "properties": {"items": {"type": "array", "minItems": 1,
                                     "items": {"type": "object", "required": ["id"]}}},
        }
        violations = SchemaValidator(schema).validate({"items": [{"nope": 1}]})
        assert violations[0].path == "items[0].id"

    def test_anyof_passes_when_one_branch_matches(self):
        schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        assert SchemaValidator(schema).is_valid(7)
        assert SchemaValidator(schema).validate({})


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------


class TestTokenBucket:
    def test_burst_then_throttle(self):
        bucket = TokenBucket(rate_per_sec=10, burst=3)
        assert [bucket.try_acquire()[0] for _ in range(3)] == [True, True, True]
        granted, wait = bucket.try_acquire()
        assert not granted and wait > 0


class TestCircuitBreaker:
    def test_opens_after_threshold_and_recovers_through_half_open(self):
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.0)
        breaker.record_failure()
        assert breaker.state is CircuitState.CLOSED
        breaker.record_failure()
        assert breaker.state is CircuitState.OPEN
        assert breaker.allows()  # timeout 0 -> immediately probes
        assert breaker.state is CircuitState.HALF_OPEN
        breaker.record_success()
        assert breaker.state is CircuitState.CLOSED

    def test_blocks_while_open(self):
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        breaker.record_failure()
        assert not breaker.allows()


class TestBackoff:
    def test_is_bounded_and_honours_retry_after(self):
        policy = BackoffPolicy(base_ms=50, max_ms=800)
        assert all(0 <= policy.delay_ms(i) <= 800 for i in range(1, 12))
        assert policy.delay_ms(1, retry_after=0.2) == pytest.approx(200.0)
        assert policy.delay_ms(1, retry_after=99) == 800.0  # capped

    def test_growth_is_exponential_without_jitter(self):
        policy = BackoffPolicy(base_ms=10, factor=2, max_ms=10_000, jitter=False)
        assert [policy.delay_ms(i) for i in range(1, 5)] == [10, 20, 40, 80]


class TestEndpointRouter:
    def test_failing_endpoint_is_deprioritised(self):
        router = EndpointRouter()
        router.register("stripe", ["a", "b", "c"])
        assert router.candidates("stripe")[0] == "a"
        router.record("stripe", "a", ok=False)
        assert router.candidates("stripe")[0] != "a"

    def test_open_breaker_endpoints_sort_last_but_stay_available(self):
        router = EndpointRouter(breaker_factory=lambda: CircuitBreaker(failure_threshold=1, recovery_timeout=60))
        router.register("telegram", ["a", "b"])
        router.record("telegram", "a", ok=False)
        assert router.candidates("telegram") == ["b", "a"]


class TestIdempotencyLedger:
    def test_replays_a_committed_result(self):
        ledger = IdempotencyLedger()
        assert ledger.lookup("k") == (False, None)
        ledger.commit("k", {"id": "tr_1"})
        assert ledger.lookup("k") == (True, {"id": "tr_1"})

    def test_a_missing_key_never_dedupes(self):
        ledger = IdempotencyLedger()
        ledger.commit(None, {"id": "x"})
        assert ledger.lookup(None) == (False, None)


class TestDriftDetector:
    def test_first_response_establishes_the_baseline(self):
        assert DriftDetector().observe("t", {"id": "a", "amount": 1}) is None

    def test_retyped_field_is_breaking(self):
        detector = DriftDetector()
        detector.observe("t", {"id": "a", "amount": 1})
        report = detector.observe("t", {"id": "a", "amount": "1"})
        assert report and report["breaking"] and report["retyped_fields"] == ["amount"]

    def test_new_optional_field_alone_is_not_breaking(self):
        detector = DriftDetector()
        detector.observe("t", {"id": "a"})
        assert detector.observe("t", {"id": "a", "new_field": 1}) is None


class TestChaosEngine:
    def test_disabled_by_default(self):
        assert ChaosEngine().maybe_fault("k", 1) is None

    def test_is_deterministic_for_a_seed(self):
        def sequence():
            engine = ChaosEngine(ChaosProfile.storm(seed=99))
            return [(f.fault.value if f else None) for f in (engine.maybe_fault("k", i) for i in range(30))]

        assert sequence() == sequence()

    def test_never_fails_more_than_max_consecutive(self):
        profile = ChaosProfile(enabled=True, seed=1, rate_limit=1.0, timeout=0, server_error=0,
                               network_partition=0, schema_drift=0, auth_expired=0, max_consecutive=2)
        engine = ChaosEngine(profile)
        results = [engine.maybe_fault("k", i) for i in range(6)]
        assert results[2] is None and results[5] is None  # forced breather


# --------------------------------------------------------------------------
# The gate itself
# --------------------------------------------------------------------------


class TestGuard:
    def test_clean_call_is_allowed_once(self):
        calls = []
        g = gate()
        outcome = g.guard(app="stripe", tool="t", payload=VALID, schema=PAYOUT_SCHEMA,
                          executor=lambda **kw: calls.append(1) or ok_executor(**kw))
        assert outcome.verdict is Verdict.ALLOW and outcome.ok and len(calls) == 1

    def test_malformed_payload_is_blocked_before_any_side_effect(self):
        calls = []
        g = gate()
        outcome = g.guard(app="stripe", tool="t", payload={**VALID, "amount": -5},
                          schema=PAYOUT_SCHEMA, executor=lambda **kw: calls.append(1))
        assert outcome.verdict is Verdict.BLOCKED
        assert calls == [], "the executor must never run on an invalid payload"

    def test_retryable_fault_is_healed(self):
        attempts = {"n": 0}

        def flaky(*, payload, endpoint):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ToolFault(FaultType.RATE_LIMITED, "429", retry_after=0.01)
            return ok_executor(payload=payload, endpoint=endpoint)

        outcome = gate().guard(app="stripe", tool="t", payload=VALID, schema=PAYOUT_SCHEMA, executor=flaky)
        assert outcome.verdict is Verdict.SELF_HEALED and outcome.ok
        assert len(outcome.attempts) == 3

    def test_terminal_fault_is_not_retried(self):
        attempts = {"n": 0}

        def denied(*, payload, endpoint):
            attempts["n"] += 1
            raise ToolFault(FaultType.PERMISSION_DENIED, "403")

        outcome = gate().guard(app="stripe", tool="t", payload=VALID, schema=PAYOUT_SCHEMA, executor=denied)
        assert outcome.verdict is Verdict.COMPENSATE
        assert attempts["n"] == 1, "a 403 must not be retried"

    def test_retries_walk_across_endpoints(self):
        seen = []

        def always_500(*, payload, endpoint):
            seen.append(endpoint)
            raise ToolFault(FaultType.SERVER_ERROR, "500")

        gate().guard(app="stripe", tool="t", payload=VALID, schema=PAYOUT_SCHEMA, executor=always_500)
        assert len(set(seen)) > 1, "the gate must reroute, not just retry the same endpoint"

    def test_idempotency_prevents_a_second_payout(self):
        calls = []
        g = gate()
        for _ in range(4):
            g.guard(app="stripe", tool="t", payload=VALID, schema=PAYOUT_SCHEMA,
                    idempotency_key="payout-1",
                    executor=lambda **kw: (calls.append(1), ok_executor(**kw))[1])
        assert len(calls) == 1, "money must move exactly once for one idempotency key"
        assert g.metrics.deduped == 3

    def test_degraded_fallback_keeps_the_saga_consistent(self):
        def always_fails(*, payload, endpoint):
            raise ToolFault(FaultType.SERVER_ERROR, "500")

        outcome = gate().guard(app="telegram", tool="t", payload=VALID, schema=PAYOUT_SCHEMA,
                               executor=always_fails,
                               degraded_executor=lambda **kw: {"queued_locally": True})
        assert outcome.verdict is Verdict.DEGRADED and outcome.ok

    def test_unexpected_exception_is_terminal_not_retried(self):
        calls = []

        def broken(*, payload, endpoint):
            calls.append(1)
            raise ValueError("a bug, not a transport fault")

        outcome = gate().guard(app="github", tool="t", payload=VALID, schema=PAYOUT_SCHEMA, executor=broken)
        assert outcome.verdict is Verdict.COMPENSATE and len(calls) == 1

    def test_breaking_drift_is_caught_and_rerouted(self):
        responses = [
            {"id": "a", "amount": 1},
            {"id": "a", "amount": "1"},   # retyped -> breaking
            {"id": "a", "amount": 2},
        ]

        def drifting(*, payload, endpoint):
            return responses.pop(0)

        g = gate()
        g.guard(app="github", tool="t", payload=VALID, schema=PAYOUT_SCHEMA, executor=drifting)  # baseline
        outcome = g.guard(app="github", tool="t", payload=VALID, schema=PAYOUT_SCHEMA, executor=drifting)
        assert outcome.ok and g.metrics.drift_events == 1

    def test_survives_a_full_chaos_storm(self):
        g = gate(chaos=ChaosProfile.storm(seed=3))
        outcomes = [
            g.guard(app="stripe", tool="t", payload=VALID, schema=PAYOUT_SCHEMA, executor=ok_executor)
            for _ in range(25)
        ]
        assert all(o.ok for o in outcomes), "every call must complete under the storm"
        assert g.metrics.faults_absorbed > 0
        assert g.metrics.reliability_score == 1.0

    def test_events_are_emitted_for_the_dashboard(self):
        seen = []
        g = gate(chaos=ChaosProfile.storm(seed=5))
        g.subscribe(seen.append)
        g.guard(app="stripe", tool="t", payload=VALID, schema=PAYOUT_SCHEMA, executor=ok_executor)
        assert {e["event"] for e in seen} & {"gate.ok", "gate.fault", "gate.backoff"}


class TestBenchmark:
    def test_reports_both_phases_with_sane_numbers(self):
        data = gate().benchmark(2000)
        for phase in ("schema_validation", "full_preflight"):
            p = data[phase]
            assert 0 < p["p50_us"] < 10_000
            assert p["p99_us"] >= p["p50_us"]
        assert data["full_preflight"]["p50_us"] >= data["schema_validation"]["p50_us"]


class TestLegacyApi:
    """The original CLI surface must keep working."""

    def test_rejects_a_payload_with_no_action(self):
        approved, reason = gate().evaluate_tool_execution("Stripe", {})
        assert not approved and "REJECTED" in reason

    def test_heals_a_retryable_simulated_error(self):
        g = gate()
        approved, reason = g.evaluate_tool_execution("Telegram", {"action": "post", "simulated_error": "RATE_LIMITED"})
        assert approved and "SELF-HEALED" in reason and g.successful_recoveries == 1


class TestFleetWideOutage:
    """When every endpoint is circuit-open, the gate probes rather than surrenders."""

    def test_probe_is_admitted_when_all_breakers_are_open(self):
        g = gate()
        for endpoint in g.router.candidates("stripe"):
            breaker = g.router.breaker(endpoint)
            for _ in range(breaker.failure_threshold):
                breaker.record_failure()
            assert not breaker.allows()

        events = []
        g.subscribe(events.append)
        outcome = g.guard(app="stripe", tool="t", payload=VALID, schema=PAYOUT_SCHEMA, executor=ok_executor)

        assert outcome.ok, "a healthy backend must still be reachable through an open fleet"
        assert any(e["event"] == "gate.forced_probe" for e in events)

    def test_probe_still_terminates_when_the_backend_is_truly_down(self):
        g = gate()
        for endpoint in g.router.candidates("stripe"):
            breaker = g.router.breaker(endpoint)
            for _ in range(breaker.failure_threshold):
                breaker.record_failure()

        def dead(*, payload, endpoint):
            raise ToolFault(FaultType.SERVER_ERROR, "500")

        outcome = g.guard(app="stripe", tool="t", payload=VALID, schema=PAYOUT_SCHEMA,
                          executor=dead, max_attempts=3)
        assert outcome.verdict is Verdict.COMPENSATE
        assert len(outcome.attempts) == 3, "the probe must not loop past the retry budget"


class TestBudgetAccounting:
    def test_open_endpoints_do_not_consume_the_retry_budget(self):
        """One dead gateway must not starve a call a healthy gateway would serve."""
        g = gate()
        endpoints = g.router.candidates("github")
        dead_breaker = g.router.breaker(endpoints[0])
        for _ in range(dead_breaker.failure_threshold):
            dead_breaker.record_failure()

        reached = []

        def executor(*, payload, endpoint):
            reached.append(endpoint)
            return ok_executor(payload=payload, endpoint=endpoint)

        outcome = g.guard(app="github", tool="t", payload=VALID, schema=PAYOUT_SCHEMA, executor=executor)
        assert outcome.ok
        assert endpoints[0] not in reached, "an open endpoint must never be selected"
