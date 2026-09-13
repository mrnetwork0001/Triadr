# ANTIGRAVITY_TRIADR - Persistent Project Context Directive

> **Project Name:** TRIADR  
> **Target Event:** Multi-App AI Agent Hackathon (`multiappagenthackathon.com`)  
> **Hackathon Date:** Sunday, September 13, 2026  
> **Target Prize:**  1st Place ($10,000 Cash + Guaranteed Founder Interview)  
> **Connected Apps:** GitHub + Telegram + Stripe  
> **Core Stack:** Model Context Protocol (MCP) + Python 3.11 + FastAPI + Next.js 14 + Tailwind CSS  

---

## Core Directives for Triadr Development

1. **Master Spec Source of Truth:**  
   Always consult [TRIADR_PROJECT_SPEC.md](file:///Users/mrnetwork/Triadr/TRIADR_PROJECT_SPEC.md).

2. **Technical Architecture Guidelines:**
   - **3 Connected Apps:** GitHub, Telegram and Stripe tool servers live in `mcp_servers/`; `agents/orchestrator.py` composes them.
   - **Self-Healing Gate:** Enforce rate-limit recovery and schema validation in `risk_gate.py`.
   - **Reliability Log:** Emit cryptographic evaluation logs in `agents/reliability_logger.py`.

3. **Submission Requirements Checklist:**
   - 3+ External Apps connected.
   - 2-Minute Demo Video walkthrough.
   - System & Reliability Brief.

4. **Repository Key Files:**
   - Master Spec: `TRIADR_PROJECT_SPEC.md`
   - Directives: `ANTIGRAVITY_TRIADR.md`
   - Self-Healing Gate: `risk_gate.py`
