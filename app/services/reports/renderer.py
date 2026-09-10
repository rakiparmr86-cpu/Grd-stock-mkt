"""Render the Report Writer agent's structured output to HTML (and optional PDF)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml", "j2"]),
)


class ReportRenderer:
    def __init__(self, out_dir: str | None = None) -> None:
        self.out_dir = Path(out_dir or settings.reports_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def render_html(self, payload: dict[str, Any]) -> str:
        tmpl = _env.get_template("report.html.j2")
        ctx = {
            "title": payload.get("title", "Analysis report"),
            "run_id": payload.get("run_id", "—"),
            "strategy": payload.get("strategy"),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "recommendation": payload.get("recommendation"),
            "chart_b64": payload.get("chart_b64"),
            "signals": payload.get("signals", []),
            "sections": payload.get("sections", []),
            "indicators": payload.get("indicators", {}),
        }
        return tmpl.render(**ctx)

    def write(self, payload: dict[str, Any], *, slug: str) -> dict[str, str]:
        html = self.render_html(payload)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        html_path = self.out_dir / f"{ts}_{slug}.html"
        html_path.write_text(html, encoding="utf-8")
        result = {"html_path": str(html_path)}

        if settings.reports_enable_pdf:
            try:
                from weasyprint import HTML  # lazy, optional dep

                pdf_path = html_path.with_suffix(".pdf")
                HTML(string=html).write_pdf(str(pdf_path))
                result["pdf_path"] = str(pdf_path)
            except Exception as exc:  # pragma: no cover
                log.warning("PDF render skipped: %s", exc)
        log.info("report written: %s", html_path)
        return result


def render_report(payload: dict[str, Any], *, slug: str = "report") -> dict[str, str]:
    return ReportRenderer().write(payload, slug=slug)
