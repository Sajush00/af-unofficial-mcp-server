"""Text rendering for CLI output (kept away from the domain modules)."""

from __future__ import annotations

from typing import Any

VERDICT_TEXT = {
    "go-now": "Much quieter than usual. Go now.",
    "good-time": "Quieter than usual. Good time to go.",
    "normal": "About normal for this hour.",
    "wait": "Busier than usual. Maybe wait an hour.",
    "skip": "Unusually packed. Skip it if you can.",
}

_BLOCKS = " ▁▂▃▄▅▆▇█"


def bar_chart(hours: list[dict[str, Any]], title: str) -> str:
    """Vertical-ish bar rows for hourly typical counts."""
    lines = [title]
    for entry in hours:
        value = int(entry["typicalCount"])
        lines.append(f"  {entry['hour']}  {value:>3}  {'█' * value}")
    return "\n".join(lines)


def heatmap(stats: dict[str, Any]) -> str:
    """Render visit_stats into a weekday x two-hour-bucket grid."""
    grid = stats["heatmap"]
    lines = ["     " + "".join(f"{h:>4}" for h in next(iter(grid.values())))]
    for day, row in grid.items():
        top = max(row.values()) or 1
        cells = ""
        for value in row.values():
            if value == 0:
                cells += "   ·"
            else:
                cells += f"  {_BLOCKS[1 + round(value / top * 7)]}"
        lines.append(f" {day}  {cells}")
    return "\n".join(lines)
