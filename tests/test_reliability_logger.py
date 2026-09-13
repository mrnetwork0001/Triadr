"""Tests for the hash-chained evaluation log - the audit trail must be tamper-evident."""

import json

import pytest

from agents.reliability_logger import GENESIS, LogEntry, ReliabilityLogger


@pytest.fixture
def log() -> ReliabilityLogger:
    logger = ReliabilityLogger("run_test")
    logger.record("run.start", {"instruction": "audit and pay"})
    logger.record("tool.call", {"ok": True}, app="github", tool="github.audit_pull_request")
    logger.record("gate.fault", {"fault": "RATE_LIMITED"}, app="telegram")
    logger.record("tool.call", {"ok": True, "amount": 250000}, app="stripe", tool="stripe.release_escrow")
    return logger


class TestChain:
    def test_first_entry_links_to_genesis(self, log):
        assert log.entries[0].prev_hash == GENESIS

    def test_each_entry_links_to_the_previous_digest(self, log):
        entries = log.entries
        for prev, curr in zip(entries, entries[1:]):
            assert curr.prev_hash == prev.digest

    def test_an_untouched_chain_verifies(self, log):
        assert log.verify()["valid"]

    def test_editing_a_payout_breaks_the_chain_at_that_entry(self, log):
        log.entries[3].payload["amount"] = 1
        log._entries[3].payload["amount"] = 1
        report = log.verify()
        assert not report["valid"] and report["broken_at"] == 3

    def test_deleting_an_entry_breaks_the_chain(self, log):
        del log._entries[2]
        log._entries[2].index = 2
        assert not log.verify()["valid"]

    def test_reordering_breaks_the_chain(self, log):
        log._entries[1], log._entries[2] = log._entries[2], log._entries[1]
        assert not log.verify()["valid"]

    def test_digest_is_deterministic(self):
        def build():
            entry = LogEntry(index=0, ts=1.5, kind="k", app="a", tool="t",
                             payload={"b": 2, "a": 1}, prev_hash=GENESIS)
            return entry.compute_digest()

        assert build() == build()

    def test_key_order_does_not_change_the_digest(self):
        a = LogEntry(0, 1.5, "k", "a", "t", {"x": 1, "y": 2}, GENESIS).compute_digest()
        b = LogEntry(0, 1.5, "k", "a", "t", {"y": 2, "x": 1}, GENESIS).compute_digest()
        assert a == b


class TestMerkleAndSignature:
    def test_merkle_root_is_stable_and_changes_with_content(self, log):
        first = log.merkle_root()
        assert first == log.merkle_root()
        log.record("run.end", {"ok": True})
        assert log.merkle_root() != first

    def test_empty_log_has_a_genesis_root(self):
        assert ReliabilityLogger("empty").merkle_root() == GENESIS

    def test_unsigned_without_a_key(self, log, monkeypatch):
        monkeypatch.delenv("TRIADR_LOG_KEY", raising=False)
        assert log.signature() is None
        assert log.attestation()["signed"] is False

    def test_signed_with_a_key(self, log, monkeypatch):
        monkeypatch.setenv("TRIADR_LOG_KEY", "hackathon-secret")
        signature = log.signature()
        assert signature and len(signature) == 64
        assert log.attestation()["signed"] is True

    def test_a_different_key_produces_a_different_signature(self, log, monkeypatch):
        monkeypatch.setenv("TRIADR_LOG_KEY", "key-a")
        a = log.signature()
        monkeypatch.setenv("TRIADR_LOG_KEY", "key-b")
        assert log.signature() != a


class TestPersistence:
    def test_round_trip_preserves_verification(self, log, tmp_path):
        paths = log.write(str(tmp_path))
        reloaded, report = ReliabilityLogger.load(paths["log"])
        assert report["valid"]
        assert len(reloaded) == len(log)
        assert reloaded.merkle_root() == log.merkle_root()

    def test_a_tampered_file_fails_verification(self, log, tmp_path):
        paths = log.write(str(tmp_path))
        lines = open(paths["log"]).read().splitlines()
        record = json.loads(lines[1])
        record["payload"]["ok"] = False
        lines[1] = json.dumps(record, sort_keys=True)
        open(paths["log"], "w").write("\n".join(lines) + "\n")

        _, report = ReliabilityLogger.load(paths["log"])
        assert not report["valid"] and report["broken_at"] == 1

    def test_attestation_file_is_written_alongside(self, log, tmp_path):
        paths = log.write(str(tmp_path))
        doc = json.loads(open(paths["attestation"]).read())
        assert doc["chain_valid"] and doc["entry_count"] == len(log)


class TestSubscribers:
    def test_listeners_receive_every_entry(self, log):
        seen = []
        log.subscribe(seen.append)
        log.record("run.end", {"ok": True})
        assert [e.kind for e in seen] == ["run.end"]

    def test_a_broken_listener_never_breaks_the_run(self, log):
        log.subscribe(lambda _entry: (_ for _ in ()).throw(RuntimeError("dashboard died")))
        log.record("run.end", {"ok": True})  # must not raise
        assert log.verify()["valid"]
