"""
Triadr - App #1: GitHub MCP server.

Tools cover the audit half of the workflow: read the pull request, read the
diff, read CI/deployment check runs, score the change, and write the verdict
back as a commit status (which is compensatable - see `github.clear_status`).

LIVE mode needs GITHUB_TOKEN. Without it the server serves deterministic
fixtures so the whole demo runs offline.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from risk_gate import FaultType, ToolFault

from .base import JSONDict, MCPServer, Mode, SideEffect, ToolSpec

_REPO = {"type": "string", "pattern": r"^[\w.\-]+/[\w.\-]+$", "description": "owner/repo"}
_PR = {"type": "integer", "minimum": 1, "description": "Pull request number"}

# Risk weights for the zero-LLM audit heuristic. Tuned so that a change touching
# payment or auth code cannot slip through on size alone.
_SENSITIVE_PATHS = (
    ("payment", 34), ("billing", 34), ("stripe", 30), ("charge", 30),
    ("auth", 28), ("token", 26), ("secret", 40), ("credential", 40),
    ("migration", 22), ("schema", 18), (".env", 45), ("dockerfile", 14),
    ("terraform", 24), ("iam", 30), ("policy", 16), ("webhook", 20),
)


class GitHubMCP(MCPServer):
    app = "github"
    api_base = "https://api.github.com"
    credential_env = ("GITHUB_TOKEN",)

    # -- shared helpers ----------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.credential('GITHUB_TOKEN')}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Accept": "application/vnd.github+json",
        }

    def _fixture_files(self, repo: str, pr: int) -> List[JSONDict]:
        rng = self._rng
        catalogue = [
            ("services/payments/stripe_client.py", 86, 12),
            ("services/payments/escrow.py", 140, 31),
            ("app/api/webhooks/route.ts", 44, 8),
            ("lib/auth/session.ts", 22, 5),
            ("db/migrations/0042_add_payout_ledger.sql", 61, 0),
            ("docs/runbook.md", 18, 2),
            ("tests/test_escrow.py", 96, 4),
            ("infra/terraform/payouts.tf", 37, 9),
        ]
        count = 3 + (pr % 4)
        picked = catalogue[: count] if count <= len(catalogue) else catalogue
        return [
            {"filename": name, "additions": add, "deletions": dele, "changes": add + dele, "status": "modified"}
            for name, add, dele in picked
        ]

    def _live_check_runs(self, repo: str, ref: str) -> List[JSONDict]:
        """CI state for a commit, from whichever API the token is allowed to read.

        Check runs need the "Checks" permission, which fine-grained tokens do not
        always offer. The combined commit-status API needs only "Commit statuses",
        which Triadr already requires for writing the verdict - so a token that can
        run the workflow can always read *some* CI signal, and a missing optional
        permission cannot fail the audit.
        """
        try:
            raw = self.http("GET", f"{self.api_base}/repos/{repo}/commits/{ref}/check-runs",
                            headers=self._headers())
            return [
                {"name": r["name"], "status": r["status"], "conclusion": r.get("conclusion"), "source": "check-runs"}
                for r in raw.get("check_runs", [])
            ]
        except ToolFault as fault:
            if fault.fault not in (FaultType.PERMISSION_DENIED, FaultType.NOT_FOUND):
                raise
        combined = self.http("GET", f"{self.api_base}/repos/{repo}/commits/{ref}/status",
                             headers=self._headers())
        conclusion = {"success": "success", "failure": "failure", "error": "failure", "pending": None}
        return [
            {"name": st.get("context", "status"),
             "status": "completed" if st.get("state") in ("success", "failure", "error") else "in_progress",
             "conclusion": conclusion.get(st.get("state")), "source": "commit-status"}
            for st in combined.get("statuses", [])
        ]

    @staticmethod
    def _score(files: List[JSONDict], checks: JSONDict) -> JSONDict:
        """Deterministic, explainable risk score - no model call on the hot path."""
        risk = 0
        reasons: List[str] = []

        churn = sum(f.get("changes", 0) for f in files)
        churn_points = min(25, churn // 20)
        if churn_points:
            risk += churn_points
            reasons.append(f"{churn} lines changed across {len(files)} files (+{churn_points})")

        for f in files:
            lowered = f.get("filename", "").lower()
            for needle, weight in _SENSITIVE_PATHS:
                if needle in lowered:
                    risk += weight
                    reasons.append(f"touches sensitive path '{needle}' in {f['filename']} (+{weight})")
                    break

        has_tests = any("test" in f.get("filename", "").lower() for f in files)
        if not has_tests:
            risk += 18
            reasons.append("no test files in the diff (+18)")
        else:
            risk = max(0, risk - 8)
            reasons.append("diff includes test coverage (-8)")

        failing = checks.get("failing", 0)
        if failing:
            risk += 30 * failing
            reasons.append(f"{failing} failing check run(s) (+{30 * failing})")
        if checks.get("state") != "success":
            risk += 12
            reasons.append(f"aggregate check state is '{checks.get('state')}' (+12)")

        risk = max(0, min(100, risk))
        band = "low" if risk < 30 else "medium" if risk < 60 else "high"
        return {
            "risk_score": risk,
            "risk_band": band,
            "requires_human_approval": risk >= 30,
            "auto_mergeable": risk < 30 and checks.get("state") == "success",
            "reasons": reasons,
        }

    # -- tools -------------------------------------------------------------

    def register_tools(self) -> None:

        @self.tool(ToolSpec(
            name="github.get_pull_request",
            app=self.app,
            title="Get pull request",
            description="Fetch a pull request's metadata: title, author, branches, mergeability and review state.",
            input_schema={
                "type": "object",
                "required": ["repo", "pr_number"],
                "properties": {"repo": _REPO, "pr_number": _PR},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["number", "title", "state", "mergeable"],
                "properties": {
                    "number": {"type": "integer"},
                    "title": {"type": "string"},
                    "author": {"type": "string"},
                    "state": {"type": "string"},
                    "mergeable": {"type": "boolean"},
                    "head_sha": {"type": "string"},
                },
            },
            side_effect=SideEffect.READ,
        ))
        def get_pull_request(args: JSONDict, ctx: JSONDict) -> JSONDict:
            repo, pr = args["repo"], args["pr_number"]
            if self.mode is Mode.LIVE:
                raw = self.http("GET", f"{self.api_base}/repos/{repo}/pulls/{pr}", headers=self._headers())
                return {
                    "number": raw["number"],
                    "title": raw["title"],
                    "author": raw.get("user", {}).get("login", "unknown"),
                    "state": raw["state"],
                    "mergeable": bool(raw.get("mergeable")),
                    "head_sha": raw["head"]["sha"],
                    "base": raw["base"]["ref"],
                    "url": raw["html_url"],
                    "_summary": f"PR #{raw['number']} '{raw['title']}' by {raw.get('user', {}).get('login')} ({raw['state']})",
                }
            self._latency(24, 70)
            sha = self._fake_id("sha", repo, pr).split("_")[1]
            return {
                "number": pr,
                "title": "Add contractor escrow release + payout ledger",
                "author": "mrnetwork",
                "state": "open",
                "mergeable": True,
                "head_sha": sha,
                "base": "main",
                "url": f"https://github.com/{repo}/pull/{pr}",
                "_summary": f"PR #{pr} 'Add contractor escrow release + payout ledger' by mrnetwork (open)",
            }

        @self.tool(ToolSpec(
            name="github.list_changed_files",
            app=self.app,
            title="List changed files",
            description="List every file changed by a pull request with per-file addition and deletion counts.",
            input_schema={
                "type": "object",
                "required": ["repo", "pr_number"],
                "properties": {"repo": _REPO, "pr_number": _PR,
                               "per_page": {"type": "integer", "minimum": 1, "maximum": 100}},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["files", "file_count", "total_changes"],
                "properties": {
                    "files": {"type": "array"},
                    "file_count": {"type": "integer", "minimum": 0},
                    "total_changes": {"type": "integer", "minimum": 0},
                },
            },
            side_effect=SideEffect.READ,
        ))
        def list_changed_files(args: JSONDict, ctx: JSONDict) -> JSONDict:
            repo, pr = args["repo"], args["pr_number"]
            if self.mode is Mode.LIVE:
                raw = self.http(
                    "GET",
                    f"{self.api_base}/repos/{repo}/pulls/{pr}/files?per_page={args.get('per_page', 100)}",
                    headers=self._headers(),
                )
                files = [
                    {"filename": f["filename"], "additions": f["additions"],
                     "deletions": f["deletions"], "changes": f["changes"], "status": f["status"]}
                    for f in raw
                ]
            else:
                self._latency(30, 95)
                files = self._fixture_files(repo, pr)
            total = sum(f["changes"] for f in files)
            return {"files": files, "file_count": len(files), "total_changes": total,
                    "_summary": f"{len(files)} files changed, {total} lines touched"}

        @self.tool(ToolSpec(
            name="github.get_check_runs",
            app=self.app,
            title="Get CI and deployment checks",
            description="Aggregate CI and deployment check-run status for a commit: build, tests, and deploy previews.",
            input_schema={
                "type": "object",
                "required": ["repo", "ref"],
                "properties": {"repo": _REPO, "ref": {"type": "string", "format": "git-ref"}},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["checks", "state", "failing"],
                "properties": {
                    "checks": {"type": "array"},
                    "state": {"type": "string", "enum": ["success", "failure", "pending"]},
                    "failing": {"type": "integer", "minimum": 0},
                },
            },
            side_effect=SideEffect.READ,
        ))
        def get_check_runs(args: JSONDict, ctx: JSONDict) -> JSONDict:
            repo, ref = args["repo"], args["ref"]
            if self.mode is Mode.LIVE:
                runs = self._live_check_runs(repo, ref)
            else:
                self._latency(20, 60)
                runs = [
                    {"name": "build", "status": "completed", "conclusion": "success"},
                    {"name": "unit-tests", "status": "completed", "conclusion": "success"},
                    {"name": "vercel/deploy-preview", "status": "completed", "conclusion": "success"},
                    {"name": "codeql", "status": "completed", "conclusion": "neutral"},
                ]
            failing = sum(1 for r in runs if r.get("conclusion") in ("failure", "timed_out", "cancelled"))
            pending = sum(1 for r in runs if r.get("status") != "completed")
            state = "failure" if failing else "pending" if pending else "success"
            return {"checks": runs, "total": len(runs), "failing": failing, "pending": pending,
                    "state": state, "_summary": f"{len(runs)} checks - state={state}, failing={failing}"}

        @self.tool(ToolSpec(
            name="github.audit_pull_request",
            app=self.app,
            title="Audit pull request",
            description=(
                "Run Triadr's deterministic risk audit on a pull request: combines diff surface, "
                "sensitive-path detection, test coverage and CI state into a 0-100 risk score with "
                "an itemised rationale and an approval requirement."
            ),
            input_schema={
                "type": "object",
                "required": ["repo", "pr_number"],
                "properties": {"repo": _REPO, "pr_number": _PR,
                               "approval_threshold": {"type": "integer", "minimum": 0, "maximum": 100}},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["risk_score", "risk_band", "requires_human_approval"],
                "properties": {
                    "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "risk_band": {"type": "string", "enum": ["low", "medium", "high"]},
                    "requires_human_approval": {"type": "boolean"},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                },
            },
            side_effect=SideEffect.READ,
        ))
        def audit_pull_request(args: JSONDict, ctx: JSONDict) -> JSONDict:
            repo, pr = args["repo"], args["pr_number"]
            meta = self.call("github.get_pull_request", {"repo": repo, "pr_number": pr}).data
            files = self.call("github.list_changed_files", {"repo": repo, "pr_number": pr}).data
            checks = self.call("github.get_check_runs", {"repo": repo, "ref": meta["head_sha"]}).data
            verdict = self._score(files["files"], checks)
            threshold = args.get("approval_threshold", 30)
            verdict["requires_human_approval"] = verdict["risk_score"] >= threshold
            verdict.update({
                "repo": repo,
                "pr_number": pr,
                "title": meta["title"],
                "author": meta["author"],
                "head_sha": meta["head_sha"],
                "url": meta["url"],
                "file_count": files["file_count"],
                "total_changes": files["total_changes"],
                "check_state": checks["state"],
                "_summary": (
                    f"PR #{pr} risk {verdict['risk_score']}/100 ({verdict['risk_band']}) - "
                    f"{'human approval required' if verdict['requires_human_approval'] else 'auto-approvable'}"
                ),
            })
            return verdict

        @self.tool(ToolSpec(
            name="github.set_commit_status",
            app=self.app,
            title="Set commit status",
            description="Write Triadr's audit verdict back onto the commit as a status check.",
            input_schema={
                "type": "object",
                "required": ["repo", "sha", "state", "description"],
                "properties": {
                    "repo": _REPO,
                    "sha": {"type": "string", "minLength": 7, "maxLength": 64},
                    "state": {"type": "string", "enum": ["error", "failure", "pending", "success"]},
                    "description": {"type": "string", "maxLength": 140},
                    "context": {"type": "string", "maxLength": 100},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["state", "sha"],
                "properties": {"state": {"type": "string"}, "sha": {"type": "string", "minLength": 7}},
            },
            side_effect=SideEffect.WRITE,
            idempotent=True,
            compensated_by="github.clear_status",
        ))
        def set_commit_status(args: JSONDict, ctx: JSONDict) -> JSONDict:
            repo, sha = args["repo"], args["sha"]
            context = args.get("context", "triadr/reliability-gate")
            if self.mode is Mode.LIVE:
                raw = self.http(
                    "POST", f"{self.api_base}/repos/{repo}/statuses/{sha}",
                    headers=self._headers(),
                    json_body={"state": args["state"], "description": args["description"], "context": context},
                )
                return {"id": raw["id"], "state": raw["state"], "context": raw["context"],
                        "sha": sha, "_summary": f"commit status '{context}' set to {raw['state']}"}
            self._latency(18, 50)
            return {"id": self._fake_id("status", repo, sha, context), "state": args["state"],
                    "context": context, "sha": sha,
                    "_summary": f"commit status '{context}' set to {args['state']}"}

        @self.tool(ToolSpec(
            name="github.clear_status",
            app=self.app,
            title="Clear commit status (compensation)",
            description="Saga compensation for github.set_commit_status - resets the status to neutral/pending.",
            input_schema={
                "type": "object",
                "required": ["repo", "sha"],
                "properties": {"repo": _REPO, "sha": {"type": "string", "minLength": 7},
                               "context": {"type": "string"}},
                "additionalProperties": False,
            },
            side_effect=SideEffect.WRITE,
            compensates="github.set_commit_status",
        ))
        def clear_status(args: JSONDict, ctx: JSONDict) -> JSONDict:
            context = args.get("context", "triadr/reliability-gate")
            if self.mode is Mode.LIVE:
                self.http("POST", f"{self.api_base}/repos/{args['repo']}/statuses/{args['sha']}",
                          headers=self._headers(),
                          json_body={"state": "pending", "description": "Triadr rolled back this run", "context": context})
            else:
                self._latency(12, 35)
            return {"reverted": True, "sha": args["sha"], "context": context,
                    "_summary": f"commit status '{context}' rolled back to pending"}
