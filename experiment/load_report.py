"""Summarise load.csv (written by loadtest.py) per strategy and request rate.

Per group: number of repeats, medians and min-max of latency and CPU, dropped iterations, error
count. Also the marginal CPU cost per extra request (least-squares slope of CPU% against achieved
req/s over a rate range, 10 * slope = ms of one core per request) and the fixed CPU level.
Only `steady` rows are summarised; `keycloak_down` rows are listed separately.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import statistics
import sys

SERVICES = ("api", "keycloak")


def number(row: dict, key: str):
    value = row.get(key, "")
    try:
        return float(value) if value not in ("", None) else None
    except ValueError:
        return None


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def spread(rows: list[dict], key: str):
    values = [v for v in (number(r, key) for r in rows) if v is not None]
    if not values:
        return None
    return {"median": statistics.median(values), "min": min(values), "max": max(values)}


def summarize(rows: list[dict]) -> list[dict]:
    groups: dict = {}
    for row in rows:
        if row.get("scenario", "steady") == "steady":
            groups.setdefault((row["strategy"], float(row["rate_target"])), []).append(row)
    summary = []
    for (strategy, rate), members in sorted(groups.items()):
        item = {"strategy": strategy, "rate": rate, "repeats": len(members),
                "errors": int(sum((number(r, "status_401") or 0) + (number(r, "status_403") or 0)
                                  + (number(r, "status_5xx") or 0) for r in members))}
        for key in ("rps", "p50_ms", "p95_ms", "p99_ms", "dropped_iterations",
                    *[f"{s}_{m}" for s in SERVICES for m in ("cpu_load_pct", "mem_max_mib")]):
            item[key] = spread(members, key)
        summary.append(item)
    return summary


def cpu_slope(rows: list[dict], strategy: str, service: str, low: float, high: float):
    """(ms of CPU per extra request, fixed CPU %), least squares over rates in [low, high]."""
    points = [(number(r, "rps"), number(r, f"{service}_cpu_load_pct")) for r in rows
              if r.get("scenario", "steady") == "steady" and r["strategy"] == strategy
              and low <= float(r["rate_target"]) <= high]
    points = [(x, y) for x, y in points if x is not None and y is not None]
    if len({x for x, _ in points}) < 2:
        return None
    mean_x = statistics.mean(x for x, _ in points)
    mean_y = statistics.mean(y for _, y in points)
    slope = (sum((x - mean_x) * (y - mean_y) for x, y in points)
             / sum((x - mean_x) ** 2 for x, _ in points))
    return {"ms_cpu_per_request": 10 * slope, "fixed_cpu_pct": mean_y - slope * mean_x}


def fmt(item, digits=1):
    return "-" if item is None else f"{item['median']:.{digits}f}"


def to_markdown(summary: list[dict]) -> str:
    lines = ["| req/s | strategie | n | p50 ms | p95 ms (min-max) | p99 ms | pierdute | erori | CPU API % | CPU KC % |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        p95 = s["p95_ms"]
        span = "-" if p95 is None else f"{p95['median']:.1f} ({p95['min']:.1f}-{p95['max']:.1f})"
        lines.append(f"| {s['rate']:g} | {s['strategy']} | {s['repeats']} | {fmt(s['p50_ms'])} | {span} | "
                     f"{fmt(s['p99_ms'])} | {fmt(s['dropped_iterations'], 0)} | {s['errors']} | "
                     f"{fmt(s['api_cpu_load_pct'])} | {fmt(s['keycloak_cpu_load_pct'])} |")
    return "\n".join(lines)


def save_plot(summary: list[dict], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(1, 3, figsize=(15, 4))
    for strategy in sorted({s["strategy"] for s in summary}):
        points = [s for s in summary if s["strategy"] == strategy]
        rates = [s["rate"] for s in points]
        axes[0].plot(rates, [s["p95_ms"]["median"] for s in points], marker="o", label=strategy)
        for axis, service in ((axes[1], "api"), (axes[2], "keycloak")):
            axis.plot(rates, [s[f"{service}_cpu_load_pct"]["median"] for s in points], marker="o", label=strategy)
    axes[0].set(title="Latență p95 (mediana repetărilor)", xlabel="cereri/s", ylabel="ms", yscale="log")
    axes[1].set(title="CPU API (100% = un nucleu)", xlabel="cereri/s", ylabel="%")
    axes[2].set(title="CPU Keycloak (100% = un nucleu)", xlabel="cereri/s", ylabel="%")
    for axis in axes:
        axis.grid(alpha=.3)
        axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def main(argv=None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("csv", type=Path, help="load.csv written by loadtest.py")
    cli.add_argument("--output", type=Path, help="JSON summary")
    cli.add_argument("--plot", type=Path, help="PNG with p95 and CPU against rate")
    cli.add_argument("--slope-range", nargs=2, type=float, default=[50, 400], metavar=("LOW", "HIGH"),
                     help="Rates (req/s) used for the marginal CPU cost; stay below saturation")
    args = cli.parse_args(argv)
    try:
        rows = read_rows(args.csv)
    except OSError:
        print("Nu pot citi fișierul.", file=sys.stderr)
        return 2
    summary = summarize(rows)
    if not summary:
        print("Niciun rând steady în fișier.", file=sys.stderr)
        return 2
    print(to_markdown(summary))
    slopes = {}
    for strategy in sorted({s["strategy"] for s in summary}):
        for service in SERVICES:
            result = cpu_slope(rows, strategy, service, *args.slope_range)
            slopes[f"{strategy}/{service}"] = result
            if result:
                print(f"{strategy:13} {service:9}: {result['ms_cpu_per_request']:.2f} ms CPU / cerere suplimentară; "
                      f"nivel fix {result['fixed_cpu_pct']:.1f}% ({args.slope_range[0]:g}-{args.slope_range[1]:g} req/s)")
    down = [r for r in rows if r.get("scenario") == "keycloak_down"]
    if down:
        print(f"{len(down)} rând(uri) keycloak_down: " + "; ".join(
            f"{r['strategy']} 200={r['status_200']} 401/403={int(float(r['status_401'] or 0) + float(r['status_403'] or 0))} "
            f"5xx={r['status_5xx']}" for r in down))
    if args.output:
        args.output.write_text(json.dumps({"groups": summary, "cpu_slopes": slopes}, indent=2), encoding="utf-8")
    if args.plot:
        save_plot(summary, args.plot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
