"""Terminal usage dashboard for `cortex stats --tui` / `--watch` (rich)."""

import json
import sys
import time

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .core.savings import totals, trend

FORMULA = (
    "observed = full file − returned chunk, once per file/session · "
    "modeled = 50% × unreturned candidate files · tokens ≈ bytes/4"
)


def _k(n) -> str:
    n = int(n or 0)
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _bar(label: str, value, total, style: str, width: int = 30) -> Text:
    frac = (value / total) if total else 0
    filled = int(round(frac * width))
    t = Text(f"{label:<9}")
    t.append("█" * filled, style=style)
    t.append("░" * (width - filled), style="dim")
    t.append(f" {_k(value)} ({frac * 100:.0f}%)")
    return t


def build_renderable(version: str, stats: dict, versions: dict | None = None):
    stats = stats if isinstance(stats, dict) else {}
    obs_code, obs_notes, modeled, total = totals(stats)
    observed = obs_code + obs_notes

    hero = Panel(
        Group(
            Text(f"{_k(total)} tokens avoided", style="bold green", justify="center"),
            Text(FORMULA, style="dim", justify="center"),
        ),
        title=f"cortex {version}",
    )
    bars = Group(_bar("observed", observed, total, "green"), _bar("modeled", modeled, total, "yellow"))

    repos = Table(title="per repo", expand=False)
    for col in ("repo", "observed", "modeled", "hits"):
        repos.add_column(col, justify="left" if col == "repo" else "right")
    by_repo = stats.get("savings_by_repo")
    rows = []
    if isinstance(by_repo, dict):
        for name, b in by_repo.items():
            if isinstance(b, dict):
                rows.append((name, b.get("observed", 0) or 0, b.get("modeled", 0) or 0, b.get("hits", 0) or 0))
    rows.sort(key=lambda r: -(r[1] + r[2]))
    for name, o, m, h in rows:
        repos.add_row(str(name), _k(o), _k(m), str(h))
    if not rows:
        repos.add_row("(none yet)", "-", "-", "-")

    parts = [hero, bars, repos]

    merged = dict(versions or {})
    merged[version] = stats
    tr = trend(merged)
    if len(tr) > 1 or (tr and tr[0][1]):
        tt = Table(title="version trend")
        tt.add_column("version")
        tt.add_column("tokens avoided", justify="right")
        for v, t in tr:
            tt.add_row(v, _k(t))
        parts.append(tt)

    unmeasured = stats.get("savings_hits_unmeasured", 0) or 0
    measured = stats.get("savings_hits_measured", 0) or 0
    parts.append(Text(f"hits measured={measured} unmeasured={unmeasured}", style="dim"))
    if unmeasured:
        parts.append(Text(f"{unmeasured} hits unmeasured: reindex to measure", style="yellow"))
    return Group(*parts)


def load_state(version: str) -> tuple:
    """Re-read stats.json from disk. Returns (stats, other_versions)."""
    from .config import stats_file
    try:
        data = json.loads(stats_file().read_text()).get("versions", {})
    except Exception:
        data = {}
    stats = data.get(version, {})
    others = {v: s for v, s in data.items() if v != version}
    return (stats if isinstance(stats, dict) else {}), others


def _console() -> Console:
    return Console()


def render(version: str, once: bool = True) -> None:
    console = _console()
    stats, others = load_state(version)
    console.print(build_renderable(version, stats, others))


def watch(version: str, interval: float = 2.0) -> None:
    console = _console()
    if not console.is_terminal:
        render(version)
        return
    from rich.live import Live
    try:
        stats, others = load_state(version)
        with Live(build_renderable(version, stats, others), console=console, refresh_per_second=4) as live:
            while True:
                time.sleep(interval)
                stats, others = load_state(version)
                live.update(build_renderable(version, stats, others))
    except KeyboardInterrupt:
        sys.exit(0)
