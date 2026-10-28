"""Render docs images from docs/e2e/plan-result.json (written by scripts/e2e.py).

- docs/plan-weeks.png: planned study hours per week, stacked by course, with the weekly budget
  and crunch weeks marked.
- docs/next7.png: the "next 7 days" view as a static card.
Run: .venv/bin/python scripts/render_docs.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9, length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plan_weeks(r: dict) -> None:
    weeks = r["plan"]["weeks"]
    courses = sorted({i["course"] for i in r["items"]})
    color = {c: SERIES[k % len(SERIES)] for k, c in enumerate(courses)}
    labels = [date.fromisoformat(w["week_start"]).strftime("%b %d") for w in weeks]
    x = range(len(weeks))
    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    style(ax)
    bottom = [0.0] * len(weeks)
    for c in courses:
        vals = [sum(b["hours"] for b in w["by_item"] if b["course"] == c) for w in weeks]
        ax.bar(x, vals, bottom=bottom, width=0.62, color=color[c], label=c,
               edgecolor=SURFACE, linewidth=1.5)
        bottom = [b + v for b, v in zip(bottom, vals)]
    budget = r["plan"]["weekly_hours"]
    ax.axhline(budget, color=INK2, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(len(weeks) - 0.5, budget + 0.6, f"{budget:g} h weekly budget", ha="right",
            va="bottom", fontsize=9, color=INK2)
    for k, w in enumerate(weeks):
        if w["is_crunch"]:
            due = sum(1 for _ in w["due_item_ids"])
            ax.text(k, bottom[k] + 0.6, f"crunch\n{due} due", ha="center", va="bottom",
                    fontsize=8.5, color=INK, fontweight="bold")
    ax.set_xticks(list(x), labels)
    ax.set_ylim(0, max(max(bottom), budget) * 1.32)
    ax.set_ylabel("planned study hours", color=INK2, fontsize=9)
    ax.set_title(f"Planned study hours per week, starting {r['today']} (crunch weeks get a longer lead)",
                 loc="left", fontsize=12, color=INK, pad=12)
    ax.legend(frameon=False, ncol=len(courses), loc="upper left", fontsize=9, labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(DOCS / "plan-weeks.png", facecolor=SURFACE)
    plt.close(fig)


def next7(r: dict) -> None:
    by_id = {i["id"]: i for i in r["items"]}
    courses = sorted({i["course"] for i in r["items"]})
    color = {c: SERIES[k % len(SERIES)] for k, c in enumerate(courses)}
    due = [by_id[i] for i in r["next7"]["due"]]
    rows = len(due)
    fig = plt.figure(figsize=(8.4, 1.25 + 0.42 * rows), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, rows + 2.6)
    n = r["next7"]
    ax.text(3, rows + 1.7, f"Due {date.fromisoformat(n['from']):%a %b %d} to {date.fromisoformat(n['to']):%a %b %d}",
            fontsize=13, color=INK, fontweight="bold", va="center")
    ax.text(3, rows + 0.95, f"{n['study_hours']:g} h of study blocks planned this week   |   "
            "every row links to the syllabus sentence it came from", fontsize=8.5, color=INK2, va="center")
    for k, it in enumerate(due):
        y = rows - k - 0.2
        when = date.fromisoformat(it["due_date"]).strftime("%a %b %d") + (f"  {it['due_time']}" if it["due_time"] else "")
        ax.text(3, y, when, fontsize=9.5, color=INK, va="center")
        ax.scatter([24.5], [y], s=40, color=color[it["course"]])
        ax.text(26, y, it["course"], fontsize=9.5, color=INK2, va="center")
        ax.text(40, y, (it["title"] if len(it["title"]) <= 42 else it["title"][:40] + "..."), fontsize=9.5, color=INK, va="center")
        ax.text(83, y, f"{it['est_hours']:g} h", fontsize=9.5, color=INK2, va="center", ha="right")
        ax.text(86, y, "verified" if it["verified"] else "check", fontsize=8.5,
                color="#0a7d0a" if it["verified"] else "#b4540a", va="center")
        ax.plot([3, 97], [y - 0.5, y - 0.5], color=GRID, linewidth=0.8)
    fig.savefig(DOCS / "next7.png", facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    r = json.loads((DOCS / "e2e" / "plan-result.json").read_text())
    plan_weeks(r)
    next7(r)
    print("wrote docs/plan-weeks.png and docs/next7.png")


if __name__ == "__main__":
    main()
