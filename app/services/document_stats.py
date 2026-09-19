"""Local (no-LLM) analysis of a document's extracted text.

Excel uploads arrive as one markdown table per sheet (``# file — sheet`` then a
pipe table); PDFs/images arrive as prose. This pulls out what can be computed
deterministically: per-sheet metric trends, key-figure lines and keywords.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_KEY_TERMS = (
    "sales", "revenue", "income", "profit", "ebitda", "eps", "margin", "debt",
    "borrowing", "equity", "assets", "liabilities", "cash", "dividend", "growth",
    "loss", "expense", "interest", "tax", "roe", "roce", "pe", "price",
)
_STOP = frozenset(
    "this that with from have been were will would their there which about into than then "
    "them they also such more most other some only over under after before between while "
    "these those where when what your ours each both being does done same very can may "
    "not and for the are was has had its our all any per nan none".split()
)
_MAX_METRICS_PER_SHEET = 40


def _num(cell: str) -> float | None:
    c = cell.strip().replace(",", "").replace("%", "").replace("₹", "").replace("$", "")
    if not c or c.lower() in {"nan", "none", "-", "—"}:
        return None
    try:
        return float(c)
    except ValueError:
        return None


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c)


def _parse_table(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    rows = [_split_row(ln) for ln in lines if ln.lstrip().startswith("|")]
    rows = [r for r in rows if not _is_separator(r)]
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _metric(label: str, values: list[float]) -> dict[str, Any]:
    first, last = values[0], values[-1]
    change = (last - first) / abs(first) * 100 if first else None
    return {
        "label": label, "count": len(values), "first": first, "latest": last,
        "min": min(values), "max": max(values), "mean": sum(values) / len(values),
        "change_pct": None if change is None else round(change, 2),
    }


def _sheet_metrics(header: list[str], body: list[list[str]]) -> list[dict[str, Any]]:
    """Row-per-metric statements (label in col 0, periods across) are the common
    Excel shape; fall back to per-column stats for tidy tables."""
    metrics: list[dict[str, Any]] = []
    for row in body:
        if len(row) < 3:
            continue
        label = row[0]
        values = [v for v in (_num(c) for c in row[1:]) if v is not None]
        if label and _num(label) is None and len(values) >= 2:
            metrics.append(_metric(label, values))
    if metrics:
        return metrics
    for j, name in enumerate(header):
        col = [_num(r[j]) for r in body if j < len(r)]
        vals = [v for v in col if v is not None]
        if name and len(vals) >= max(2, len(col) // 2):
            metrics.append(_metric(name, vals))
    return metrics


def _priority(m: dict[str, Any]) -> int:
    lab = m["label"].lower()
    return 0 if any(t in lab for t in _KEY_TERMS) else 1


def analyze_text(text: str) -> dict[str, Any]:
    """Return {overview, sheets, key_lines, keywords} for the document text."""
    sections: list[tuple[str, list[str]]] = []
    name, buf = "document", []
    for line in text.splitlines():
        if line.startswith("# "):
            if buf:
                sections.append((name, buf))
            name, buf = line[2:].strip(), []
        else:
            buf.append(line)
    if buf:
        sections.append((name, buf))

    sheets: list[dict[str, Any]] = []
    for name, lines in sections:
        header, body = _parse_table(lines)
        if not body:
            continue
        metrics = sorted(_sheet_metrics(header, body), key=_priority)
        sheets.append({
            "name": name, "rows": len(body), "columns": len(header), "header": header,
            "metrics": metrics[:_MAX_METRICS_PER_SHEET],
        })

    words = re.findall(r"[A-Za-z][A-Za-z&-]{3,}", text)
    counts = Counter(w.lower() for w in words if w.lower() not in _STOP)
    keywords = [{"term": t, "count": c} for t, c in counts.most_common(15)]

    key_lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("|") or s.startswith("#") or len(s) < 12:
            continue
        low = s.lower()
        if any(t in low.split() or t in low for t in _KEY_TERMS[:14]) and re.search(r"\d", s):
            key_lines.append(s[:240])
        if len(key_lines) >= 10:
            break

    return {
        "overview": {
            "characters": len(text), "words": len(words),
            "sheets_or_tables": len(sheets),
        },
        "sheets": sheets,
        "key_lines": key_lines,
        "keywords": keywords,
    }


def _fmt(v: float) -> str:
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def report_sections(stats: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn ``analyze_text`` output into renderer sections."""
    ov = stats["overview"]
    out: list[dict[str, Any]] = [{
        "heading": "Overview",
        "body": (f"{ov['words']:,} words extracted; {ov['sheets_or_tables']} "
                 f"table(s)/sheet(s) with numeric data."),
        "bullets": [],
    }]
    for sh in stats["sheets"]:
        bullets = []
        for m in sh["metrics"][:12]:
            chg = "" if m["change_pct"] is None else f", {m['change_pct']:+.1f}% first→latest"
            bullets.append(f"{m['label']}: {_fmt(m['first'])} → {_fmt(m['latest'])} "
                           f"(min {_fmt(m['min'])}, max {_fmt(m['max'])}{chg})")
        out.append({
            "heading": f"Sheet: {sh['name']}",
            "body": f"{sh['rows']} rows × {sh['columns']} columns.",
            "bullets": bullets or ["No numeric series found."],
        })
    if stats["key_lines"]:
        out.append({"heading": "Key figure lines", "body": "", "bullets": stats["key_lines"]})
    if stats["keywords"]:
        out.append({
            "heading": "Frequent terms", "body": "",
            "bullets": [f"{k['term']} ({k['count']})" for k in stats["keywords"]],
        })
    return out
