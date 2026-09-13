"""
Triadr brand glyph for text-only surfaces (Telegram, CLI, receipts).

The web UI renders the real mark (components/TriadrMark.tsx). Channels that
cannot render SVG get this one consistent glyph instead of assorted emoji, so
a Telegram card, a CLI banner and a receipt all read as the same product.
"""

TRIADR_MARK = "◈"  # ◈ - a waypoint: the gate every side effect passes through

RISK_BADGE = {"low": "[LOW]", "medium": "[MEDIUM]", "high": "[HIGH]"}
