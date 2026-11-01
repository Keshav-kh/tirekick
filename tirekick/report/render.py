"""Render the HTML report for /r/{deal_id}. Owner: A."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from tirekick.models import Deal, Severity

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)
_ORDER = {Severity.RED: 0, Severity.YELLOW: 1, Severity.GREEN: 2}


def money(amount: int | None, currency: str = "USD") -> str:
    if amount is None:
        return "-"
    return f"${amount:,}" if currency == "USD" else f"{currency} {amount:,}"


def render_report(deal: Deal) -> str:
    report = deal.report
    evidence = sorted(report.evidence, key=lambda e: _ORDER[e.severity]) if report else []
    return _env.get_template("report.html").render(
        deal=deal, report=report, evidence=evidence, money=money,
        frame_url=lambda e: f"/r/{deal.deal_id}/frames/{Path(e.highlight_path or e.frame_path).name}"
        if (e.highlight_path or e.frame_path) else None,
    )
