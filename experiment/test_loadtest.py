"""Deterministic tests for loadtest.py; no Docker, k6, Keycloak or API."""
import contextlib
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import loadtest
import measure

STATS = "\n".join(json.dumps(row) for row in (
    {"Name": "securesync-api-1", "CPUPerc": "35.50%", "MemUsage": "512MiB / 7.6GiB"},
    {"Name": "securesync-keycloak-1", "CPUPerc": "120.00%", "MemUsage": "1.5GiB / 7.6GiB"},
    {"Name": "securesync-api-db-1", "CPUPerc": "1.00%", "MemUsage": "40MiB / 7.6GiB"},
    {"Name": "other-thing", "CPUPerc": "99%", "MemUsage": "1MiB / 2MiB"},
))
CLAIMS = {"exp": 1060.0, "iat": 1000.0, "sub": "s", "sid": "x"}


def args(**over):
    base = dict(strategy="jwt", duration=30, idle_seconds=6, guard=5.0, stats_interval=0.01,
                endpoint="/api/me", api_url="http://localhost:8081", issuer="http://localhost:8080/realms/securesync",
                audience="securesync-api", request_timeout=1, ready_timeout=10)
    base.update(over)
    return SimpleNamespace(**base)


def k6_data(rps=100.0, **statuses):
    return {"data": {"requests": rps * 30, "rps": rps, "failed_ratio": 0.0, "dropped_iterations": 0},
            "latency": {"p50": 4.0, "p95": 9.0, "p99": 15.0, "max": 40.0},
            "statuses": {"200": rps * 30, "401": 0, "403": 0, "5xx": 0, "other": 0, **statuses}}


class Sampler:
    """Stands in for StatsSampler with fixed readings."""
    def __init__(self, readings):
        self.samples = readings
    def __call__(self, interval):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False


class ParsingTests(unittest.TestCase):
    def test_sizes_use_binary_and_decimal_units(self):
        self.assertEqual(loadtest.parse_size("1KiB"), 1024)
        self.assertEqual(loadtest.parse_size("2.5MB"), 2_500_000)
        self.assertAlmostEqual(loadtest.parse_size("1.5GiB"), 1.5 * 1024 ** 3)
        self.assertIsNone(loadtest.parse_size("12 parsecs"))
        self.assertIsNone(loadtest.parse_size("--"))

    def test_docker_stats_picks_only_the_two_services(self):
        found = loadtest.parse_docker_stats(STATS)
        self.assertEqual(set(found), {"api", "keycloak"})
        self.assertEqual(found["api"]["cpu_pct"], 35.5)
        self.assertEqual(found["api"]["mem_bytes"], 512 * 1024 ** 2)
        self.assertEqual(found["keycloak"]["cpu_pct"], 120.0)

    def test_malformed_lines_are_skipped_not_guessed(self):
        text = "not json\n" + json.dumps({"Name": "securesync-api-1", "CPUPerc": "abc", "MemUsage": "1MiB / 2MiB"}) \
            + "\n" + json.dumps({"Name": "securesync-api-1"}) + "\n"
        self.assertEqual(loadtest.parse_docker_stats(text), {})
        self.assertEqual(loadtest.parse_docker_stats(""), {})

    def test_summary_and_cost_per_request(self):
        samples = [{"api": {"cpu_pct": 40.0, "mem_bytes": 100 * 1024 ** 2}},
                   {"api": {"cpu_pct": 60.0, "mem_bytes": 120 * 1024 ** 2}}]
        summary = loadtest.summarize_stats(samples, "api")
        self.assertEqual(summary["cpu_mean"], 50.0)
        self.assertEqual(summary["mem_max_mib"], 120.0)
        self.assertEqual(loadtest.summarize_stats(samples, "keycloak"), {"cpu_mean": None, "mem_max_mib": None, "n": 0})
        # (50 - 10)% of one core = 400 ms/s over 100 req/s = 4 ms per request.
        self.assertAlmostEqual(loadtest.cpu_ms_per_request(50.0, 10.0, 100.0), 4.0)
        self.assertEqual(loadtest.cpu_ms_per_request(5.0, 10.0, 100.0), 0.0, "never negative")
        self.assertIsNone(loadtest.cpu_ms_per_request(None, 10.0, 100.0))
        self.assertIsNone(loadtest.cpu_ms_per_request(50.0, 10.0, 0))

    def test_k6_summary_is_validated(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "k6.json"
            path.write_text(json.dumps({**k6_data()["data"], "latency_ms": k6_data()["latency"],
                                        "statuses": k6_data()["statuses"]}), encoding="utf-8")
            self.assertEqual(loadtest.read_k6_summary(path)["latency"]["p95"], 9.0)
            path.write_text('{"requests": 1}', encoding="utf-8")
            with self.assertRaises(measure.ExperimentError):
                loadtest.read_k6_summary(path)
            with self.assertRaises(measure.ExperimentError):
                loadtest.read_k6_summary(Path(directory) / "missing.json")

    def test_rates_are_validated(self):
        self.assertEqual(loadtest.parse_rates("25, 50,100"), [25.0, 50.0, 100.0])
        for bad in ("", "0", "-5", "abc", "9999"):
            with self.assertRaises(Exception):
                loadtest.parse_rates(bad)


class DeniedDiagnosticsTests(unittest.TestCase):
    def test_sampled_reasons_are_deduplicated_and_time_free(self):
        log = "\n".join([
            'time="x" level=info msg="DENIED_REASON 401 t=12.3s Bearer error=\\"invalid_token\\", error_description=\\"Provided token isn\'t active\\"" source=console',
            'DENIED_REASON 401 t=13.9s Bearer error="invalid_token", error_description="Provided token isn\'t active"',
            "unrelated line", "DENIED_REASON 403 t=1.0s"])
        reasons = loadtest.denied_reasons(log)
        self.assertTrue(all("t=" not in r for r in reasons))
        self.assertGreaterEqual(len(reasons), 1)
        self.assertIn("401", reasons[0])
        self.assertEqual(loadtest.denied_reasons("nothing here"), [])
        self.assertLessEqual(len(loadtest.denied_reasons("\n".join(f"DENIED_REASON 40{i} t=1s r{i}" for i in range(9)))), 3)


class ProbeTests(unittest.TestCase):
    def test_probe_failure_carries_the_apis_reason_but_not_the_token(self):
        class Reply:
            status_code = 401
            headers = {"WWW-Authenticate": 'Bearer error="invalid_token", error_description="The iss claim is not valid"'}
        with patch.object(measure, "request", return_value=Reply()):
            with self.assertRaises(measure.ExperimentError) as caught:
                loadtest.probe_strategy(args(), "secret-token")
        self.assertIn("probe_http_401", str(caught.exception))
        self.assertIn("The iss claim is not valid", str(caught.exception))
        self.assertNotIn("secret-token", str(caught.exception))
        self.assertEqual(loadtest.bearer_error(SimpleNamespace(headers={})), "")


class ScenarioTests(unittest.TestCase):
    def scenario(self, *, strategy="jwt", probe_result="jwt", idle=True, around=None, now=1000.0,
                 k6_status=None, idle_samples=None, load_samples=None):
        calls = []
        def fake_k6(a, token, rate, summary):
            calls.append(("k6", rate))
            summary.write_text(json.dumps({**k6_data(**(k6_status or {}))["data"],
                                           "latency_ms": k6_data()["latency"],
                                           "statuses": k6_data(**(k6_status or {}))["statuses"]}), encoding="utf-8")
        samplers = iter([Sampler(idle_samples or []), Sampler(load_samples or [])] if idle else [Sampler(load_samples or [])])
        with patch.object(measure, "token_metadata", return_value=CLAIMS):
            row = loadtest.run_scenario(args(strategy=strategy), 100.0, lambda: "token", "steady", idle=idle,
                                        around=around or (lambda: contextlib.nullcontext()), k6=fake_k6,
                                        sampler=lambda interval: next(samplers),
                                        probe=lambda a, t: probe_result, sleep=lambda s: calls.append(("sleep", s)),
                                        wall_clock=lambda: now)
        return row, calls

    def test_row_combines_k6_and_docker_numbers(self):
        idle = [{"api": {"cpu_pct": 10.0, "mem_bytes": 400 * 1024 ** 2}}]
        load = [{"api": {"cpu_pct": 50.0, "mem_bytes": 500 * 1024 ** 2}, "keycloak": {"cpu_pct": 80.0, "mem_bytes": 1024 ** 3}}]
        row, calls = self.scenario(idle_samples=idle, load_samples=load)
        self.assertEqual(calls, [("sleep", 6), ("k6", 100.0)])
        self.assertEqual(row["rps"], 100.0)
        self.assertEqual(row["p95_ms"], 9.0)
        self.assertAlmostEqual(row["api_cpu_ms_per_request"], 4.0)
        self.assertIsNone(row["keycloak_cpu_ms_per_request"], "no idle reading for keycloak")
        self.assertEqual(row["keycloak_mem_max_mib"], 1024.0)
        self.assertEqual((row["stats_samples"], row["idle_samples"]), (1, 1))

    def test_docker_unavailable_leaves_stats_blank_but_keeps_k6_numbers(self):
        row, _ = self.scenario()
        self.assertEqual(row["rps"], 100.0)
        self.assertIsNone(row["api_cpu_load_pct"])
        self.assertEqual(row["stats_samples"], 0)

    def test_strategy_mismatch_stops_before_any_load(self):
        with self.assertRaises(measure.ExperimentError) as caught:
            self.scenario(strategy="introspection", probe_result="jwt")
        self.assertEqual(str(caught.exception), "api_strategy_differs_from_requested_strategy")

    def test_token_must_outlive_load_and_guard(self):
        # The token is fresh when the load starts: it only has to cover duration + guard = 35 s.
        with self.assertRaises(measure.ExperimentError) as caught:
            self.scenario(now=1030.0)  # 30 s left < 35 s
        self.assertEqual(str(caught.exception), "token_lifetime_too_short_for_duration")
        self.scenario(now=1020.0)  # 40 s left >= 35 s, with the idle phase too
        self.scenario(now=1020.0, idle=False)

    def test_token_is_requested_after_the_idle_phase_not_before(self):
        order = []
        def source():
            order.append("token")
            return "token"
        def fake_k6(a, token, rate, summary):
            order.append("k6")
            summary.write_text(json.dumps({**k6_data()["data"], "latency_ms": k6_data()["latency"],
                                           "statuses": k6_data()["statuses"]}), encoding="utf-8")
        with patch.object(measure, "token_metadata", return_value=CLAIMS):
            loadtest.run_scenario(args(), 100.0, source, "steady", k6=fake_k6,
                                  sampler=lambda interval: Sampler([]), probe=lambda a, t: "jwt",
                                  sleep=lambda s: order.append("idle"), wall_clock=lambda: 1000.0)
        self.assertEqual(order, ["idle", "token", "k6"])

    def test_denials_are_recorded_not_hidden(self):
        row, _ = self.scenario(k6_status={"200": 0, "401": 3000})
        self.assertEqual(row["status_401"], 3000)
        self.assertEqual(row["status_200"], 0)


class KeycloakDownTests(unittest.TestCase):
    def test_keycloak_is_always_restarted_and_awaited(self):
        order = []
        ready = iter([False, False, True])
        with self.assertRaises(RuntimeError):
            with loadtest.keycloak_stopped(args(), run_compose=lambda *a: order.append(a[0]),
                                           ready=lambda a: next(ready), sleep=lambda s: order.append("wait"),
                                           clock=lambda: 0):
                order.append("load")
                raise RuntimeError("k6 failed")
        self.assertEqual(order, ["stop", "load", "start", "wait", "wait"])

    def test_restart_timeout_is_reported(self):
        ticks = iter(range(0, 1000, 5))
        with self.assertRaises(measure.ExperimentError) as caught:
            with loadtest.keycloak_stopped(args(ready_timeout=10), run_compose=lambda *a: None,
                                           ready=lambda a: False, sleep=lambda s: None, clock=lambda: next(ticks)):
                pass
        self.assertEqual(str(caught.exception), "keycloak_not_ready_after_restart")


class MainTests(unittest.TestCase):
    def run_main(self, argv, scenario, env=None):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", {"DEMO_USER_PASSWORD": "demo-pass", **(env or {})}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = loadtest.main(argv, scenario=scenario, login=lambda s, a, u, p: "token")
        return code, out.getvalue(), err.getvalue()

    def test_sweep_writes_one_csv_row_per_rate_and_no_token_or_password(self):
        with TemporaryDirectory() as directory:
            rows = []
            def scenario(a, rate, token, name, **kw):
                rows.append((rate, name, kw["idle"]))
                return loadtest.build_row(a, name, rate, k6_data(rate), [], [])
            code, out, err = self.run_main(["--strategy", "jwt", "--rates", "10,20", "--warmup-seconds", "0", "--output", directory], scenario)
            self.assertEqual(code, 0)
            self.assertEqual(rows, [(10.0, "steady", True), (20.0, "steady", True)])
            text = (Path(directory) / "load.csv").read_text(encoding="utf-8")
            parsed = list(csv.DictReader(io.StringIO(text)))
            self.assertEqual([r["rate_target"] for r in parsed], ["10.0", "20.0"])
            self.assertNotIn("token", text.lower().replace("token_", ""))
            self.assertNotIn("demo-pass", text + out + err)

    def test_keycloak_down_adds_the_lowest_rate_without_idle(self):
        with TemporaryDirectory() as directory:
            seen = []
            def scenario(a, rate, token, name, **kw):
                seen.append((rate, name, kw["idle"]))
                return loadtest.build_row(a, name, rate, k6_data(rate), [], [])
            code, *_ = self.run_main(["--strategy", "jwt", "--rates", "50,10", "--keycloak-down", "--warmup-seconds", "0", "--output", directory], scenario)
            self.assertEqual(code, 0)
            self.assertEqual(seen[-1], (10.0, "keycloak_down", False))

    def test_missing_password_or_k6_stops_with_code_2(self):
        def boom(*a, **k):
            raise measure.ExperimentError("k6_not_installed")
        with TemporaryDirectory() as directory:
            code, _, err = self.run_main(["--strategy", "jwt", "--rates", "10", "--warmup-seconds", "0", "--output", directory], boom)
            self.assertEqual(code, 2)
            self.assertIn("k6_not_installed", err)
            self.assertFalse((Path(directory) / "load.csv").exists(), "no invented rows")

    def test_warmup_runs_once_before_the_sweep_and_is_not_recorded(self):
        import time as _time
        calls = []
        def scenario(a, rate, token, name, **kw):
            calls.append(("scenario", rate))
            return loadtest.build_row(a, name, rate, k6_data(rate), [], [])
        def warm(a, token, rate):
            calls.append(("warmup", rate, a.warmup_seconds))
        with TemporaryDirectory() as directory, patch.object(measure, "token_metadata",
                                                           return_value={"exp": _time.time() + 60}):
            out, err = io.StringIO(), io.StringIO()
            with patch.dict("os.environ", {"DEMO_USER_PASSWORD": "demo-pass"}), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = loadtest.main(["--strategy", "jwt", "--rates", "100,50,400", "--warmup-seconds", "20",
                                      "--output", directory], scenario=scenario,
                                     login=lambda s, a, u, p: "token", warmup=warm)
            rows = list(csv.DictReader(io.StringIO((Path(directory) / "load.csv").read_text(encoding="utf-8"))))
        self.assertEqual(code, 0)
        self.assertEqual(calls[0], ("warmup", 100.0, 20), "median of the rates")
        self.assertEqual([c for c in calls if c[0] == "scenario"], [("scenario", 100.0), ("scenario", 50.0), ("scenario", 400.0)])
        self.assertEqual(len(rows), 3, "the warm-up adds no CSV row")

    def test_repeats_and_shuffle_cover_every_rate_each_time_and_are_reproducible(self):
        def run(extra):
            seen = []
            def scenario(a, rate, token, name, **kw):
                seen.append(rate)
                return loadtest.build_row(a, name, rate, k6_data(rate), [], [])
            with TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()), \
                    patch.dict("os.environ", {"DEMO_USER_PASSWORD": "demo-pass"}):
                code = loadtest.main(["--strategy", "jwt", "--rates", "10,20,30,40", "--warmup-seconds", "0",
                                      "--output", directory, *extra], scenario=scenario,
                                     login=lambda s, a, u, p: "token")
                rows = len(list(csv.DictReader(io.StringIO((Path(directory) / "load.csv").read_text(encoding="utf-8")))))
            self.assertEqual(code, 0)
            return seen, rows
        plain, rows = run([])
        self.assertEqual((plain, rows), ([10.0, 20.0, 30.0, 40.0], 4))
        shuffled, rows = run(["--repeats", "3", "--shuffle", "--seed", "7"])
        self.assertEqual(rows, 12)
        for repeat in range(3):
            self.assertEqual(sorted(shuffled[repeat * 4:(repeat + 1) * 4]), [10.0, 20.0, 30.0, 40.0])
        self.assertNotEqual(shuffled[:4], shuffled[4:8], "each repeat has its own order")
        self.assertEqual(run(["--repeats", "3", "--shuffle", "--seed", "7"])[0], shuffled)

    def test_warmup_can_be_disabled_and_must_fit_the_token(self):
        calls = []
        def scenario(a, rate, token, name, **kw):
            return loadtest.build_row(a, name, rate, k6_data(rate), [], [])
        with TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"DEMO_USER_PASSWORD": "demo-pass"}), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = loadtest.main(["--strategy", "jwt", "--rates", "10", "--warmup-seconds", "0",
                                      "--output", directory], scenario=scenario,
                                     login=lambda s, a, u, p: "token", warmup=lambda *a: calls.append(a))
            self.assertEqual((code, calls), (0, []))
        with TemporaryDirectory() as directory, patch.object(measure, "token_metadata", return_value={"exp": 0}):
            err = io.StringIO()
            with patch.dict("os.environ", {"DEMO_USER_PASSWORD": "demo-pass"}), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = loadtest.main(["--strategy", "jwt", "--rates", "10", "--output", directory],
                                     scenario=scenario, login=lambda s, a, u, p: "token", warmup=lambda *a: None)
            self.assertEqual(code, 2)
            self.assertIn("token_lifetime_too_short_for_warmup", err.getvalue())

    def test_input_validation(self):
        for bad in (["--endpoint", "/other"], ["--endpoint", "/api/x?y=1"], ["--keycloak-url", "http://example.com:8080"]):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                loadtest.main(["--strategy", "jwt", *bad], scenario=None, login=None)


if __name__ == "__main__":
    unittest.main()
