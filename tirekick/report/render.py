"""Render the HTML report for /r/{deal_id}. Owner: A."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from tirekick import config
from tirekick.models import Deal, DealStatus, Severity

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)
_ORDER = {Severity.RED: 0, Severity.YELLOW: 1, Severity.GREEN: 2}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".3gp", ".webm"}


def money(amount: int | None, currency: str = "USD") -> str:
    if amount is None:
        return "-"
    return f"${amount:,}" if currency == "USD" else f"{currency} {amount:,}"


def mmss(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def proof_video_path(deal: Deal) -> Path | None:
    """The seller's proof video, only if it lives under data/ (dev paths can point anywhere)."""
    if not (deal.report and deal.report.analysis):
        return None
    path = Path(deal.report.analysis.video_path).resolve()
    if path.suffix.lower() in VIDEO_SUFFIXES and path.is_relative_to(config.DATA_DIR.resolve()) and path.is_file():
        return path
    return None


def render_report(deal: Deal) -> str:
    report = deal.report
    evidence = sorted(report.evidence, key=lambda e: _ORDER[e.severity]) if report else []
    counts = {s.value: sum(e.severity == s for e in evidence) for s in Severity}
    agreed = deal.negotiation.last_offer if deal.status == DealStatus.AGREED and deal.negotiation else None
    return _env.get_template("report.html").render(
        deal=deal, report=report, evidence=evidence, money=money, mmss=mmss, counts=counts, agreed=agreed,
        video_url=f"/r/{deal.deal_id}/video" if proof_video_path(deal) else None,
        frame_url=lambda e: f"/r/{deal.deal_id}/frames/{Path(e.highlight_path or e.frame_path).name}"
        if (e.highlight_path or e.frame_path) else None,
    )
