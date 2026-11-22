"""Analyze real SecureSync measurements, keeping censored and invalid runs visible."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import random
import statistics


def quantile(values, probability):
    ordered = sorted(values)
    if not ordered:
        return None
    location = (len(ordered) - 1) * probability
    lower = math.floor(location)
    fraction = location - lower
    return ordered[lower] + fraction * (ordered[math.ceil(location)] - ordered[lower])


def finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("CSV contains an invalid number") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError("CSV contains a negative or non-finite number")
    return number


def distribution(values):
    return {"n": len(values), "min": min(values) if values else None,
            "p50": quantile(values, 0.5), "p95": quantile(values, 0.95),
            "p99": quantile(values, 0.99),
            "max": max(values) if values else None,
            "mean": statistics.fmean(values) if values else None}


def ecdf(values):
    """Empirical CDF as sorted values and their cumulative probabilities (right-continuous steps)."""
    ordered = sorted(values)
    count = len(ordered)
    return {"values": ordered, "cumulative_probability": [(index + 1) / count for index in range(count)]}


def denial_pairs(group):
    """(token lifetime left at revocation, time to deny) for confirmed denials that record both."""
    pairs = []
    for row in group:
        if row["outcome"] != "denied" or not row.get("remaining_at_revoke_s"):
            continue
        pairs.append([finite_number(row["remaining_at_revoke_s"]), finite_number(row["time_to_deny_s"])])
    return pairs


def bootstrap_median_ci(values, repetitions=2000, seed=2026):
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    ordered = sorted(values)
    medians = [statistics.median(rng.choices(ordered, k=len(ordered))) for _ in range(repetitions)]
    return [quantile(medians, 0.025), quantile(medians, 0.975)]


def read_csv(path: Path, fields):
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if not fields.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"Missing CSV columns in {path.name}")
        return list(reader)


def load_data(inputs):
    runs, samples, seen_paths = [], [], set()
    for input_path in inputs:
        run_path = input_path / "runs.csv" if input_path.is_dir() else input_path
        run_path = run_path.resolve()
        if run_path in seen_paths:
            continue
        seen_paths.add(run_path)
        runs.extend(read_csv(run_path, {"run_id", "strategy", "outcome", "time_to_deny_s", "token_ttl_s"}))
        sample_path = run_path.parent / "samples.csv"
        if sample_path.exists():
            samples.extend(read_csv(sample_path, {"run_id", "strategy", "phase", "latency_ms", "status"}))
    run_ids = [row["run_id"] for row in runs]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Duplicate run IDs; avoid including the same results twice")
    if any(row["strategy"] not in ("jwt", "introspection") or
           row["outcome"] not in ("denied", "censored", "invalid") for row in runs):
        raise ValueError("Unknown strategy or outcome in runs.csv")
    by_run = {row["run_id"]: row for row in runs}
    for row in samples:
        if row["run_id"] not in by_run:
            # An interrupted write may leave samples without a completed run summary.
            continue
        if row["strategy"] != by_run[row["run_id"]]["strategy"]:
            raise ValueError("Sample strategy does not match its run")
        finite_number(row["latency_ms"])
    return runs, samples


def analyze(runs, samples, bootstrap=2000):
    output = {"method": {
        "time_to_deny": "First denial response completion after successful revocation, confirmed by at least 5 consecutive 401/403 responses",
        "censored": "No confirmed denial within the observation window; excluded from denial quantiles, reported explicitly",
        "invalid": "Network errors, unexpected HTTP responses or failed baseline; excluded from latency and denial summaries",
        "latency": "Pooled baseline HTTP-200 latencies; medians per run are also reported",
        "bootstrap": "Percentile 95% CI of median, resampling runs; fixed random seed 2026",
        "p99": "Interpolated quantile; it is informative only with about 100 or more confirmed runs, so read it with n",
        "ecdf": "Empirical CDF of confirmed time-to-deny values; censored and invalid runs are not included",
        "denial_minus_remaining_s": "Time to deny minus token lifetime left at revocation: near 0 or slightly positive "
                                    "when the token is refused only at expiry, clearly negative when refused earlier",
    }, "groups": []}
    # TTL is part of the grouping: combining different token lifetimes would distort revocation comparisons.
    keys = sorted({(r["strategy"], int(finite_number(r["token_ttl_s"]))) for r in runs})
    for strategy, ttl in keys:
        group = [r for r in runs if r["strategy"] == strategy and int(float(r["token_ttl_s"])) == ttl]
        denied = [finite_number(r["time_to_deny_s"]) for r in group if r["outcome"] == "denied"]
        valid_ids = {r["run_id"] for r in group if r["outcome"] != "invalid"}
        baseline_by_run = {run_id: [] for run_id in sorted(valid_ids)}
        for row in samples:
            if row["run_id"] in valid_ids and row["phase"] == "baseline" and row["status"] == "200":
                baseline_by_run[row["run_id"]].append(finite_number(row["latency_ms"]))
        baseline = [value for values in baseline_by_run.values() for value in values]
        medians = [statistics.median(values) for values in baseline_by_run.values() if values]
        pairs = denial_pairs(group)
        offsets = [deny - remaining for remaining, deny in pairs]
        group_output = {
            "strategy": strategy, "token_ttl_s": ttl, "runs_total": len(group),
            "runs_denied": sum(r["outcome"] == "denied" for r in group),
            "runs_censored": sum(r["outcome"] == "censored" for r in group),
            "runs_invalid": sum(r["outcome"] == "invalid" for r in group),
            "time_to_deny_s": distribution(denied),
            "median_time_to_deny_95pct_ci_s": bootstrap_median_ci(denied, bootstrap),
            "time_to_deny_ecdf": ecdf(denied),
            "denial_vs_remaining_s": pairs,
            "denial_minus_remaining_s": {"n": len(offsets), "min": min(offsets) if offsets else None,
                                         "p50": quantile(offsets, 0.5),
                                         "max": max(offsets) if offsets else None},
            "baseline_request_latency_ms": distribution(baseline),
            "baseline_median_per_run_ms": distribution(medians),
            "median_baseline_run_latency_95pct_ci_ms": bootstrap_median_ci(medians, bootstrap),
            "censored_observation_s": [finite_number(r.get("observation_s", "0")) for r in group
                                       if r["outcome"] == "censored"],
            "errors": sorted({r.get("error", "") for r in group if r.get("error")}),
        }
        output["groups"].append(group_output)
    return output


def save_plot(summary, path: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        raise ValueError("Install matplotlib to use --plot") from None
    groups = summary["groups"]
    if not groups:
        raise ValueError("No measurements available to plot")
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    for axis, key, title, unit in (
            (axes[0], "time_to_deny_s", "Revocation window among confirmed runs", "seconds"),
            (axes[1], "baseline_request_latency_ms", "Baseline request latency", "milliseconds")):
        axis.set_title(title)
        axis.set_ylabel(unit)
        labels = []
        for index, group in enumerate(groups):
            stats = group[key]
            labels.append(f"{group['strategy']}\nTTL {group['token_ttl_s']}s\n"
                          f"denied {group['runs_denied']}, censored {group['runs_censored']}, "
                          f"invalid {group['runs_invalid']}")
            if stats["p50"] is not None:
                axis.scatter(index, stats["p50"], marker="o", label="p50" if index == 0 else None)
                axis.scatter(index, stats["p95"], marker="x", label="p95" if index == 0 else None)
        axis.set_xticks(range(len(groups)), labels, fontsize=8)
        axis.set_ylim(bottom=0)
        axis.grid(axis="y", alpha=0.25)
        if axis.collections:
            axis.legend()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def save_ecdf_plot(summary, path: Path):
    """ECDF of time-to-deny per group, and time-to-deny against token lifetime left at revocation."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        raise ValueError("Install matplotlib to use --ecdf-plot") from None
    groups = [group for group in summary["groups"] if group["time_to_deny_ecdf"]["values"]]
    if not groups:
        raise ValueError("No confirmed denials available to plot")
    figure, (cdf_axis, pair_axis) = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    for group in groups:
        label = f"{group['strategy']}, TTL {group['token_ttl_s']}s (n={group['time_to_deny_s']['n']})"
        cdf = group["time_to_deny_ecdf"]
        cdf_axis.step(cdf["values"], cdf["cumulative_probability"], where="post", label=label)
        if group["denial_vs_remaining_s"]:
            remaining, deny = zip(*group["denial_vs_remaining_s"])
            pair_axis.scatter(remaining, deny, s=14, alpha=0.7, label=label)
    cdf_axis.set(title="ECDF of time to deny (confirmed runs)", xlabel="seconds",
                 ylabel="cumulative probability", ylim=(0, 1.02))
    cdf_axis.set_xlim(left=0)
    cdf_axis.grid(alpha=0.25)
    cdf_axis.legend(fontsize=8)
    limit = max([point for group in groups for pair in group["denial_vs_remaining_s"] for point in pair] or [1])
    pair_axis.plot([0, limit], [0, limit], linestyle="--", linewidth=1, color="gray",
                   label="denied exactly at token expiry")
    pair_axis.set(title="Time to deny vs lifetime left at revocation", xlabel="lifetime left (s)",
                  ylabel="time to deny (s)")
    pair_axis.set_xlim(left=0)
    pair_axis.set_ylim(bottom=0)
    pair_axis.grid(alpha=0.25)
    pair_axis.legend(fontsize=8)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("inputs", type=Path, nargs="*", default=[Path(__file__).resolve().parent / "data"])
    cli.add_argument("--output", type=Path, help="Write JSON summary")
    cli.add_argument("--plot", type=Path, help="Write comparison PNG; needs matplotlib")
    cli.add_argument("--ecdf-plot", type=Path, help="Write ECDF and denial-vs-lifetime PNG; needs matplotlib")
    cli.add_argument("--bootstrap", type=int, default=2000)
    args = cli.parse_args(argv)
    if args.bootstrap < 100:
        cli.error("--bootstrap must be at least 100")
    try:
        runs, samples = load_data(args.inputs)
        if not runs:
            raise ValueError("No completed measurement runs found")
        summary = analyze(runs, samples, args.bootstrap)
        text = json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)
        if args.plot:
            save_plot(summary, args.plot)
        if args.ecdf_plot:
            save_ecdf_plot(summary, args.ecdf_plot)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + "\n", encoding="utf-8")
        print(text)
    except (ValueError, OSError) as error:
        cli.exit(2, f"Analysis failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
