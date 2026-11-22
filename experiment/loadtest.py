"""Cost of token validation under load: k6 requests plus `docker stats` CPU and memory.

For every request rate the script logs in with a fresh Keycloak session (batch.form_login_token,
Authorization Code with S256 PKCE, demo credentials only from the local environment), checks
that the API runs the requested strategy, measures the idle CPU/memory of the containers, runs
k6/k6-api.js at a constant arrival rate and appends one row to load.csv. Optionally it repeats
the lowest rate with Keycloak stopped to see which strategy keeps validating tokens.

Nothing here is a benchmark result by itself: the numbers depend on the machine, Docker's VM
and what else is running. Keep both strategies on the same machine and settings.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable
from urllib.parse import quote, urlsplit

import requests

import batch
import measure

ROOT = Path(__file__).resolve().parents[1]
K6_SCRIPT = Path(__file__).resolve().parent / "load" / "k6-api.js"
SERVICES = ("api", "keycloak")
FIELDS = [
    "scenario", "strategy", "endpoint", "rate_target", "duration_s", "requests", "rps",
    "failed_ratio", "dropped_iterations", "p50_ms", "p95_ms", "p99_ms", "max_ms",
    "status_200", "status_401", "status_403", "status_5xx", "status_other",
    "stats_samples", "idle_samples",
    *[f"{service}_{metric}" for service in SERVICES
      for metric in ("cpu_idle_pct", "cpu_load_pct", "cpu_ms_per_request", "mem_max_mib")],
]
SIZE_UNITS = {"b": 1, "kb": 1000, "mb": 1000 ** 2, "gb": 1000 ** 3, "tb": 1000 ** 4,
              "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4}


def parse_size(text: str) -> float | None:
    """'256.4MiB' -> bytes; None when the text is not a size."""
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)\s*", text or "")
    unit = SIZE_UNITS.get(match.group(2).lower()) if match else None
    return float(match.group(1)) * unit if match and unit else None


def parse_docker_stats(text: str, services=SERVICES) -> dict:
    """Pick the compose services out of `docker stats --no-stream --format '{{json .}}'`.

    Container names look like `securesync-api-1`. Malformed lines are skipped, never guessed.
    """
    found = {}
    for line in text.splitlines():
        try:
            row = json.loads(line)
            name, cpu, memory = row["Name"], row["CPUPerc"], row["MemUsage"]
            cpu_pct = float(cpu.strip().rstrip("%"))
            mem_bytes = parse_size(memory.split("/")[0])
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        if mem_bytes is None:
            continue
        for service in services:
            if service not in found and re.fullmatch(rf".*[-_]{re.escape(service)}[-_]\d+", name):
                found[service] = {"cpu_pct": cpu_pct, "mem_bytes": mem_bytes}
    return found


def docker_stats_text() -> str:
    """One `docker stats` reading; empty text when Docker is unavailable (reported as blank)."""
    try:
        done = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}"],
                              capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


class StatsSampler:
    """Reads docker stats in a background thread until stop() is called."""

    def __init__(self, interval: float, read: Callable[[], str] = docker_stats_text):
        self.interval, self.read = interval, read
        self.samples: list[dict] = []
        self._stop, self._thread = threading.Event(), None

    def _loop(self):
        while not self._stop.is_set():
            reading = parse_docker_stats(self.read())
            if reading:
                self.samples.append(reading)
            self._stop.wait(self.interval)

    def __enter__(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=35)


def summarize_stats(samples: list[dict], service: str) -> dict:
    """Mean CPU % and peak memory of one service; None when it never appeared."""
    cpu = [s[service]["cpu_pct"] for s in samples if service in s]
    memory = [s[service]["mem_bytes"] for s in samples if service in s]
    if not cpu:
        return {"cpu_mean": None, "mem_max_mib": None, "n": 0}
    return {"cpu_mean": sum(cpu) / len(cpu), "mem_max_mib": max(memory) / 1024 ** 2, "n": len(cpu)}


def cpu_ms_per_request(load_pct: float | None, idle_pct: float | None, rps: float | None):
    """Extra CPU time per request, in ms of one core. docker stats reports 100% per core."""
    if load_pct is None or idle_pct is None or not rps or rps <= 0:
        return None
    return max(0.0, load_pct - idle_pct) / 100 * 1000 / rps


def read_k6_summary(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        latency, statuses = data["latency_ms"], data["statuses"]
        for key in ("requests", "rps", "failed_ratio", "dropped_iterations"):
            if not isinstance(data[key], (int, float)):
                raise ValueError(key)
        for key in ("p50", "p95", "p99", "max"):
            if not isinstance(latency[key], (int, float)):
                raise ValueError(key)
        return {"data": data, "latency": latency, "statuses": statuses}
    except (OSError, ValueError, KeyError, TypeError):
        raise measure.ExperimentError("k6_summary_missing_or_invalid") from None


def denied_reasons(text: str, limit: int = 3) -> list[str]:
    """Distinct sampled DENIED_REASON lines from the k6 log, with the time part removed."""
    found = []
    for line in text.splitlines():
        match = re.search(r"DENIED_REASON (\d{3}) t=[0-9.]+s ?(.*)", line)
        if match:
            reason = "".join(c for c in f"{match.group(1)} {match.group(2)}" if c.isprintable())[:200].rstrip('"\' ')
            if reason not in found:
                found.append(reason)
        if len(found) >= limit:
            break
    return found


def run_k6(args, token: str, rate: float, summary: Path) -> None:
    binary = shutil.which(args.k6)
    if not binary:
        raise measure.ExperimentError("k6_not_installed")
    env = {**os.environ, "SECURESYNC_ACCESS_TOKEN": token, "API_URL": args.api_url,
           "ENDPOINT": args.endpoint, "RATE": str(rate), "DURATION": str(args.duration),
           "SUMMARY_PATH": str(summary)}
    try:
        done = subprocess.run([binary, "run", "--quiet", str(K6_SCRIPT)], env=env,
                              capture_output=True, text=True, timeout=args.duration + 120, check=False)
    except subprocess.TimeoutExpired:
        raise measure.ExperimentError("k6_timeout") from None
    except OSError:
        raise measure.ExperimentError("k6_not_runnable") from None
    if done.returncode != 0:
        # k6 output can echo URLs; keep the terminal detail generic.
        raise measure.ExperimentError(f"k6_exit_{done.returncode}")
    reasons = denied_reasons(done.stderr + done.stdout)
    if reasons:
        summary.with_name("denied-reasons.txt").write_text("\n".join(reasons), encoding="utf-8")


def bearer_error(response) -> str:
    """The API's own WWW-Authenticate reason (for example 'Jwt expired'), truncated and printable.

    The header comes from the API, never contains the token, and tells a bad issuer or audience
    apart from an unreachable JWKS endpoint.
    """
    header = (getattr(response, "headers", None) or {}).get("WWW-Authenticate", "")
    text = "".join(c for c in header if c.isprintable())[:160]
    return f" ({text})" if text else ""


def run_warmup(args, token: str, rate: float) -> None:
    """Throwaway k6 run: lets the JVM (JIT), connection pools and caches settle. Not recorded."""
    warm = argparse.Namespace(**{**vars(args), "duration": args.warmup_seconds})
    with tempfile.TemporaryDirectory() as directory:
        run_k6(warm, token, rate, Path(directory) / "warmup.json")


def probe_strategy(args, token: str) -> str:
    """GET /api/me once: proves the token works and reports the API's active strategy."""
    with requests.Session() as session:
        response = measure.request(session, "GET", f"{args.api_url}/api/me", args.request_timeout,
                                   headers={"Authorization": f"Bearer {token}"})
    if response.status_code != 200:
        raise measure.ExperimentError(f"probe_http_{response.status_code}{bearer_error(response)}")
    return measure.response_json(response, "invalid_probe_response").get("strategy")


def compose(*arguments: str) -> None:
    try:
        done = subprocess.run(["docker", "compose", *arguments], cwd=ROOT, capture_output=True,
                              text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        raise measure.ExperimentError("docker_compose_unavailable") from None
    if done.returncode != 0:
        raise measure.ExperimentError(f"docker_compose_{arguments[0]}_failed")


def keycloak_ready(args) -> bool:
    url = f"{args.issuer}/.well-known/openid-configuration"
    try:
        with requests.Session() as session:
            return measure.request(session, "GET", url, args.request_timeout).status_code == 200
    except measure.ExperimentError:
        return False


@contextlib.contextmanager
def keycloak_stopped(args, *, run_compose=compose, ready=keycloak_ready,
                     sleep=time.sleep, clock=time.monotonic):
    """Stop Keycloak for the body; always start it again and wait until it answers."""
    run_compose("stop", "keycloak")
    try:
        yield
    finally:
        run_compose("start", "keycloak")
        deadline = clock() + args.ready_timeout
        while not ready(args):
            if clock() > deadline:
                raise measure.ExperimentError("keycloak_not_ready_after_restart")
            sleep(3)


def run_scenario(args, rate: float, token_source: Callable[[], str], scenario: str, *, idle: bool = True,
                 around=lambda: contextlib.nullcontext(), k6=run_k6,
                 sampler=StatsSampler, probe=probe_strategy,
                 sleep=time.sleep, wall_clock=time.time) -> dict:
    """One row: idle sample, then a FRESH token, probe, constant-rate load, load sample.

    The token is requested only after the idle phase. Reading docker stats on a machine that was
    just saturated can take seconds, and a token obtained earlier could expire during the load,
    turning the last seconds into 401s that say nothing about the strategy.
    """
    idle_samples = []
    if idle:
        with sampler(args.stats_interval) as idle_sampler:
            sleep(args.idle_seconds)
        idle_samples = idle_sampler.samples
    token = token_source()
    claims = measure.token_metadata(token, args.issuer, args.audience)
    if claims["exp"] - wall_clock() < args.duration + args.guard:
        raise measure.ExperimentError("token_lifetime_too_short_for_duration")
    if probe(args, token) != args.strategy:
        raise measure.ExperimentError("api_strategy_differs_from_requested_strategy")
    with tempfile.TemporaryDirectory() as directory:
        summary = Path(directory) / "k6.json"
        with around():
            with sampler(args.stats_interval) as load_sampler:
                k6(args, token, rate, summary)
        result = read_k6_summary(summary)
        reasons_file = summary.with_name("denied-reasons.txt")
        reasons = reasons_file.read_text(encoding="utf-8").splitlines() if reasons_file.exists() else []
    row = build_row(args, scenario, rate, result, idle_samples, load_sampler.samples)
    # Console-only diagnostics (not CSV columns, so the CSV schema stays stable).
    row["_denied_at_s"] = result["data"].get("denied_at_s")
    row["_denied_reasons"] = reasons
    return row


def build_row(args, scenario, rate, result, idle_samples, load_samples) -> dict:
    data, latency, statuses = result["data"], result["latency"], result["statuses"]
    row = {"scenario": scenario, "strategy": args.strategy, "endpoint": args.endpoint,
           "rate_target": rate, "duration_s": args.duration, "requests": data["requests"],
           "rps": data["rps"], "failed_ratio": data["failed_ratio"],
           "dropped_iterations": data["dropped_iterations"], "p50_ms": latency["p50"],
           "p95_ms": latency["p95"], "p99_ms": latency["p99"], "max_ms": latency["max"],
           "stats_samples": len(load_samples), "idle_samples": len(idle_samples)}
    for key in ("200", "401", "403", "5xx", "other"):
        row[f"status_{key}"] = statuses.get(key, 0)
    for service in SERVICES:
        idle, load = summarize_stats(idle_samples, service), summarize_stats(load_samples, service)
        row[f"{service}_cpu_idle_pct"] = idle["cpu_mean"]
        row[f"{service}_cpu_load_pct"] = load["cpu_mean"]
        row[f"{service}_cpu_ms_per_request"] = cpu_ms_per_request(load["cpu_mean"], idle["cpu_mean"], data["rps"])
        row[f"{service}_mem_max_mib"] = load["mem_max_mib"]
    return row


def append_row(directory: Path, row: dict) -> None:
    path = directory / "load.csv"
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if new:
            writer.writeheader()
        writer.writerow({key: ("" if row.get(key) is None else row[key]) for key in FIELDS})


def parse_rates(value: str) -> list[float]:
    try:
        rates = [float(part) for part in value.split(",") if part.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError("Use a comma-separated list of positive numbers") from None
    if not rates or any(rate <= 0 or rate > 5000 for rate in rates):
        raise argparse.ArgumentTypeError("Rates must be in (0, 5000] requests/s")
    return rates


def parser():
    cli = argparse.ArgumentParser(prog="loadtest.py", description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--strategy", required=True, choices=("jwt", "introspection"))
    cli.add_argument("--rates", type=parse_rates, default=[50.0, 100.0, 200.0, 400.0, 800.0],
                     help="Constant request rates (req/s), comma-separated")
    cli.add_argument("--repeats", type=measure.positive_int, default=1,
                     help="Repeat the whole list of rates; each rate adds one CSV row per repeat")
    cli.add_argument("--shuffle", action="store_true",
                     help="Random rate order in every repeat (seeded by --seed), so order effects average out")
    cli.add_argument("--seed", type=int, default=2026, help="Seed of the --shuffle order")
    cli.add_argument("--duration", type=measure.positive_int, default=30, help="Seconds of load per rate")
    cli.add_argument("--idle-seconds", type=measure.positive_int, default=15,
                     help="Idle sampling before each load, to subtract baseline CPU")
    cli.add_argument("--warmup-seconds", type=int, default=20,
                     help="Throwaway load before the sweep so JIT and pools settle; 0 disables it")
    cli.add_argument("--warmup-rate", type=measure.positive_float, default=None,
                     help="Rate of the warm-up (default: the median of --rates)")
    cli.add_argument("--stats-interval", type=measure.positive_float, default=1.0,
                     help="Pause between docker stats readings (each reading takes about 1-2 s)")
    cli.add_argument("--guard", type=measure.positive_float, default=5.0,
                     help="Seconds of token lifetime left unused after the load")
    cli.add_argument("--endpoint", default="/api/me",
                     help="/api/me isolates token validation; /api/documents adds policy and database")
    cli.add_argument("--keycloak-down", action="store_true",
                     help="After the sweep, repeat the lowest rate with Keycloak stopped (restarted afterwards)")
    cli.add_argument("--ready-timeout", type=measure.positive_float, default=180,
                     help="Seconds to wait for Keycloak after restarting it")
    cli.add_argument("--k6", default="k6", help="k6 executable")
    cli.add_argument("--api-url", type=measure.safe_base_url, default="http://localhost:8081")
    cli.add_argument("--keycloak-url", type=measure.safe_base_url, default="http://localhost:8080")
    cli.add_argument("--realm", default="securesync")
    cli.add_argument("--audience", default="securesync-api")
    cli.add_argument("--client-id", default="securesync-experiment")
    cli.add_argument("--callback-port", type=measure.positive_int, default=8765)
    cli.add_argument("--username", default="alice.it", help="Synthetic demo user with USER or ADMIN")
    cli.add_argument("--request-timeout", type=measure.positive_float, default=5)
    cli.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "data" / "load")
    return cli


def main(argv=None, scenario: Callable = run_scenario, login: Callable = batch.form_login_token,
         warmup: Callable = run_warmup):
    cli = parser()
    args = cli.parse_args(argv)
    if not 1 <= args.callback_port <= 65535:
        cli.error("--callback-port must be between 1 and 65535")
    if (not args.endpoint.startswith("/api/") or any(c in args.endpoint for c in ("?", "#", "\\"))
            or ".." in args.endpoint):
        cli.error("--endpoint must be a fixed /api/ path without query or traversal")
    if args.warmup_seconds < 0:
        cli.error("--warmup-seconds must be 0 or positive")
    if urlsplit(args.keycloak_url).hostname not in batch.LOOPBACK_HOSTS:
        cli.error("The demo password is sent only to a loopback Keycloak")
    args.issuer = f"{args.keycloak_url}/realms/{quote(args.realm, safe='')}"
    try:
        password = batch.demo_password()
        args.output.mkdir(parents=True, exist_ok=True)
        if args.warmup_seconds:
            warm_rate = args.warmup_rate or sorted(args.rates)[len(args.rates) // 2]
            with requests.Session() as session:
                token = login(session, args, args.username, password)
            claims = measure.token_metadata(token, args.issuer, args.audience)
            if claims["exp"] - time.time() < args.warmup_seconds + args.guard:
                raise measure.ExperimentError("token_lifetime_too_short_for_warmup")
            print(f"{args.strategy}: încălzire {warm_rate:g} cereri/s, {args.warmup_seconds} s (nu se înregistrează) ...", flush=True)
            warmup(args, token, warm_rate)
        plan = []
        for repeat in range(args.repeats):
            order = list(args.rates)
            if args.shuffle:
                random.Random(args.seed + repeat).shuffle(order)
            plan += [(rate, "steady", False) for rate in order]
        if args.keycloak_down:
            plan.append((min(args.rates), "keycloak_down", True))
        def fresh_token():
            with requests.Session() as session:
                return login(session, args, args.username, password)

        for rate, name, down in plan:
            print(f"{args.strategy}: {name}, {rate:g} cereri/s, {args.duration} s ...", flush=True)
            around = (lambda: keycloak_stopped(args)) if down else (lambda: contextlib.nullcontext())
            row = scenario(args, rate, fresh_token, name, idle=not down, around=around)
            append_row(args.output, row)
            print(f"  rps {row['rps']:.1f}; p95 {row['p95_ms']:.1f} ms; 200={row['status_200']} "
                  f"4xx={row['status_401'] + row['status_403']} 5xx={row['status_5xx']}; "
                  f"cădere={row['dropped_iterations']}", flush=True)
            if name == "steady" and row["status_401"] + row["status_403"]:
                print("  ATENȚIE: 401/403 într-un scenariu steady. Cu introspecție pot fi erori interne ale API-ului "
                      "mascate ca 401; numără-le: docker compose logs --since 30m api | "
                      "grep -c \"AuthenticationServiceException: I/O error\". Nu interpreta rândul fără cauză.", flush=True)
                at = row.get("_denied_at_s")
                if at and at.get("min") is not None:
                    print(f"  refuzuri între secundele {at['min']:.1f} și {at['max']:.1f} ale testului "
                          f"(mediana {at['med']:.1f}); în ultimele secunde înseamnă token expirat, "
                          f"dispersate înseamnă refuzuri sub încărcare.", flush=True)
                for reason in row.get("_denied_reasons") or []:
                    print(f"  motiv API: {reason}", flush=True)
    except (measure.ExperimentError, OSError) as error:
        reason = str(error) if isinstance(error, measure.ExperimentError) else "local_file_error"
        print(f"Experiment oprit: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
