"""Deterministic regression tests; no Keycloak, database or real user sessions."""
import argparse
import base64
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from unittest.mock import patch

import requests

import analyze
import measure


ISSUER = "http://localhost:8080/realms/securesync"


def token(**overrides):
    claims = {"sub": "synthetic-user", "sid": "synthetic-session", "iss": ISSUER,
              "aud": ["securesync-api"], "iat": 990, "exp": 1050}
    claims.update(overrides)
    return "test." + measure.b64url(json.dumps(claims).encode()) + ".test"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, value):
        self.now += value


class Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self.body = body

    def json(self):
        return self.body


class Session:
    def __init__(self, clock, statuses, strategy="jwt", revoke_status=204):
        self.clock, self.statuses = clock, iter(statuses)
        self.strategy, self.revoke_status = strategy, revoke_status
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        self.clock.sleep(0.02)
        if url.endswith("/api/me"):
            return Response(200, {"sub": "synthetic-user", "strategy": self.strategy})
        if method == "DELETE":
            return Response(self.revoke_status)
        status = next(self.statuses, 200)
        if isinstance(status, Exception):
            raise status
        return Response(status)


def args(**overrides):
    options = dict(strategy="jwt", issuer=ISSUER, audience="securesync-api", ttl=None,
                   api_url="http://localhost:8081", keycloak_url="http://localhost:8080",
                   realm="securesync", endpoint="/api/documents", request_timeout=1,
                   baseline_requests=2, confirmations=5, interval=0.1, max_wait=1)
    options.update(overrides)
    return SimpleNamespace(**options)


class MeasurementTests(unittest.TestCase):
    def run_measurement(self, statuses, options=None, **session_options):
        clock = Clock()
        session = Session(clock, statuses, **session_options)
        result = measure.measure_run(options or args(), token(), "admin-test", session,
                                     clock, lambda: 1000 + clock.now, clock.sleep)
        return result, session

    def test_confirms_first_denial_after_five_consecutive_denials(self):
        (result, samples, revoked_at), session = self.run_measurement([200, 200] + [401] * 5)
        self.assertEqual(result.outcome, "denied")
        self.assertAlmostEqual(result.time_to_deny_s, 0.02)
        self.assertEqual(len(samples), 7)
        self.assertIsNotNone(revoked_at)
        self.assertGreater(result.remaining_at_revoke_s, 0)
        delete = next(call for call in session.calls if call[0] == "DELETE")
        self.assertTrue(delete[1].endswith("/sessions/synthetic-session?isOffline=false"))
        self.assertTrue(all(call[2]["allow_redirects"] is False for call in session.calls))
        self.assertTrue(all(call[0] != "POST" for call in session.calls))

    def test_a_success_resets_denial_streak(self):
        (result, samples, _), _session = self.run_measurement([200, 200, 401, 401, 200] + [403] * 5,
                                                             args(max_wait=3))
        self.assertEqual(result.outcome, "denied")
        self.assertAlmostEqual(result.time_to_deny_s, samples[5].completed - samples[2].started)

    def test_forbidden_baseline_is_invalid_and_does_not_revoke(self):
        (result, _samples, _), session = self.run_measurement([403])
        self.assertEqual(result.outcome, "invalid")
        self.assertEqual(result.error, "baseline_http_403")
        self.assertFalse(any(call[0] == "DELETE" for call in session.calls))

    def test_wrong_server_strategy_does_not_revoke(self):
        (result, _samples, _), session = self.run_measurement([], strategy="introspection")
        self.assertEqual(result.error, "api_strategy_differs_from_requested_strategy")
        self.assertEqual(len(session.calls), 1)

    def test_http_500_is_not_counted_as_denial(self):
        (result, _samples, _), _session = self.run_measurement([200, 200, 500])
        self.assertEqual(result.outcome, "invalid")
        self.assertIsNone(result.time_to_deny_s)
        self.assertEqual(result.error, "probe_http_500")

    def test_network_error_is_not_counted_as_denial(self):
        (result, _samples, _), _session = self.run_measurement([200, 200, requests.ConnectionError("private")])
        self.assertEqual(result.outcome, "invalid")
        self.assertEqual(result.error, "network_error")

    def test_timeout_and_short_denial_streak_are_censored(self):
        for statuses in ([200, 200], [200, 200, 401, 401]):
            with self.subTest(statuses=statuses):
                (result, _samples, _), _session = self.run_measurement(statuses, args(max_wait=0.2))
                self.assertEqual(result.outcome, "censored")
                self.assertIsNone(result.time_to_deny_s)

    def test_a_denial_response_outside_the_window_is_censored(self):
        (result, _samples, _), _session = self.run_measurement([200, 200] + [401] * 5,
                                                             args(max_wait=0.005))
        self.assertEqual(result.outcome, "censored")

    def test_late_http_error_is_invalid_rather_than_censored(self):
        (result, _samples, _), _session = self.run_measurement([200, 200, 503], args(max_wait=0.005))
        self.assertEqual(result.outcome, "invalid")
        self.assertEqual(result.error, "probe_http_503")

    def test_revocation_must_return_204(self):
        (result, _samples, revoked_at), _session = self.run_measurement([200, 200], revoke_status=404)
        self.assertEqual(result.error, "revocation_http_404")
        self.assertEqual(result.outcome, "invalid")
        self.assertIsNone(revoked_at)

    def test_requested_ttl_is_checked_not_reconfigured(self):
        (result, _samples, _), session = self.run_measurement([], args(ttl=10))
        self.assertEqual(result.error, "token_ttl_differs_from_requested_ttl")
        self.assertEqual(session.calls, [])

    def test_metadata_requires_expected_issuer_audience_and_session(self):
        for overrides in ({"iss": "http://elsewhere"}, {"aud": "wrong"}, {"sid": ""},
                          {"iat": True}, {"exp": float("nan")}):
            with self.subTest(overrides=overrides), self.assertRaises(measure.ExperimentError):
                measure.token_metadata(token(**overrides), ISSUER, "securesync-api")

    def test_metadata_accepts_string_audience(self):
        self.assertEqual(measure.token_metadata(token(aud="securesync-api"), ISSUER,
                                               "securesync-api")["sid"], "synthetic-session")

    def test_unencrypted_credentials_only_allowed_on_loopback(self):
        for value in ("http://remote.example", "https://user:pass@example.test", "ftp://localhost"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                measure.safe_base_url(value)
        self.assertEqual(measure.safe_base_url("http://localhost:8080/"), "http://localhost:8080")

    def test_csv_contains_no_access_or_admin_tokens(self):
        (result, samples, revoked_at), _session = self.run_measurement([200, 200] + [401] * 5)
        with TemporaryDirectory() as directory:
            measure.write_run(Path(directory), result, samples, revoked_at)
            text = "".join(path.read_text() for path in Path(directory).glob("*.csv"))
            self.assertNotIn(token(), text)
            self.assertNotIn("admin-test", text)
            self.assertNotIn("synthetic-session", text)
            with (Path(directory) / "samples.csv").open(newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertLess(float(rows[0]["offset_s"]), 0)
            self.assertGreater(float(rows[-1]["offset_s"]), 0)

    def test_existing_csv_schema_is_not_silently_corrupted(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "runs.csv"
            path.write_text("other,column\n")
            with self.assertRaises(measure.ExperimentError):
                measure.append_csv(path, measure.RUN_FIELDS, [])

    def test_complete_cli_through_loopback_http_without_real_keycloak(self):
        state = {"revoked": False}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def respond(self, status, body=None):
                payload = b"" if body is None else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                if self.path == "/api/me":
                    self.respond(200, {"sub": "synthetic-user", "strategy": "jwt"})
                elif self.path == "/api/documents":
                    self.respond(401 if state["revoked"] else 200, [])
                else:
                    self.respond(404)

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.respond(200, {"access_token": "synthetic-admin-token"})

            def do_DELETE(self):
                if self.path == "/admin/realms/securesync/sessions/synthetic-session?isOffline=false":
                    state["revoked"] = True
                    self.respond(204)
                else:
                    self.respond(404)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        real_time = measure.time.time()
        live_token = token(iss=base_url + "/realms/securesync", iat=int(real_time), exp=int(real_time) + 60)
        try:
            with TemporaryDirectory() as directory, patch.dict(measure.os.environ, {
                "EXPERIMENT_ADMIN_CLIENT_SECRET": "synthetic-secret", "SECURESYNC_ACCESS_TOKEN": live_token
            }), patch("builtins.print"):
                exit_code = measure.main(["--strategy", "jwt", "--api-url", base_url,
                                          "--keycloak-url", base_url, "--interval", "0.001",
                                          "--baseline-requests", "2", "--output", directory])
                self.assertEqual(exit_code, 0)
                rows, samples = analyze.load_data([Path(directory)])
                self.assertEqual(rows[0]["outcome"], "denied")
                self.assertEqual(len(samples), 7)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class AnalysisTests(unittest.TestCase):
    @staticmethod
    def run_row(run_id, outcome="denied", strategy="jwt", ttl="60", delay="1", error=""):
        return dict(run_id=run_id, outcome=outcome, strategy=strategy, token_ttl_s=ttl,
                    time_to_deny_s=delay if outcome == "denied" else "", error=error, observation_s="90")

    def test_does_not_turn_censored_or_invalid_runs_into_fast_denials(self):
        rows = [self.run_row("a", delay="2"), self.run_row("b", delay="4"),
                self.run_row("c", "censored"), self.run_row("d", "invalid", error="network_error")]
        samples = [dict(run_id="a", phase="baseline", status="200", latency_ms="10"),
                   dict(run_id="d", phase="baseline", status="200", latency_ms="0.001")]
        group = analyze.analyze(rows, samples, 100)["groups"][0]
        self.assertEqual(group["runs_total"], 4)
        self.assertEqual(group["runs_censored"], 1)
        self.assertEqual(group["runs_invalid"], 1)
        self.assertEqual(group["time_to_deny_s"]["p50"], 3)
        self.assertEqual(group["baseline_request_latency_ms"]["p50"], 10)

    def test_groups_different_strategies_and_lifetimes(self):
        rows = [self.run_row("a"), self.run_row("b", ttl="30"),
                self.run_row("c", strategy="introspection")]
        self.assertEqual(len(analyze.analyze(rows, [], 100)["groups"]), 3)

    def test_bootstrap_is_repeatable_and_absent_for_single_run(self):
        self.assertEqual(analyze.bootstrap_median_ci([1, 2, 3], 100),
                         analyze.bootstrap_median_ci([1, 2, 3], 100))
        self.assertIsNone(analyze.bootstrap_median_ci([1]))
        self.assertEqual(analyze.bootstrap_median_ci([1, 2, 3], 100),
                         analyze.bootstrap_median_ci([3, 1, 2], 100))

    def test_analysis_of_only_censored_runs_has_no_denial_quantiles(self):
        group = analyze.analyze([self.run_row("a", "censored")], [], 100)["groups"][0]
        self.assertIsNone(group["time_to_deny_s"]["p50"])
        self.assertEqual(group["time_to_deny_s"]["n"], 0)

    def test_invalid_numbers_are_rejected(self):
        for value in ("nan", "inf", "-1", "word"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                analyze.finite_number(value)

    def test_round_trip_raw_csv(self):
        clock = Clock()
        session = Session(clock, [200, 200] + [401] * 5)
        result, samples, revoked_at = measure.measure_run(args(), token(), "admin-test", session,
                                                         clock, lambda: 1000 + clock.now, clock.sleep)
        with TemporaryDirectory() as directory:
            measure.write_run(Path(directory), result, samples, revoked_at)
            runs, loaded_samples = analyze.load_data([Path(directory)])
            group = analyze.analyze(runs, loaded_samples, 100)["groups"][0]
            self.assertEqual(group["runs_denied"], 1)
            self.assertEqual(group["baseline_request_latency_ms"]["n"], 2)

    def test_invalid_metadata_remains_visible_in_unknown_ttl_group(self):
        rows = [self.run_row("valid"), self.run_row("invalid", "invalid", ttl="0",
                                                    error="invalid_token_metadata")]
        groups = analyze.analyze(rows, [], 100)["groups"]
        unknown = next(group for group in groups if group["token_ttl_s"] == 0)
        self.assertEqual(unknown["runs_invalid"], 1)
        self.assertEqual(unknown["time_to_deny_s"]["n"], 0)

    def test_sample_strategy_mismatch_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)
            row = self.run_row("synthetic")
            measure.append_csv(path / "runs.csv", list(row), [row])
            measure.append_csv(path / "samples.csv", measure.SAMPLE_FIELDS, [{
                "run_id": "synthetic", "strategy": "introspection", "phase": "baseline",
                "offset_s": -1, "latency_ms": 1, "status": 200,
            }])
            with self.assertRaisesRegex(ValueError, "strategy"):
                analyze.load_data([path])


if __name__ == "__main__":
    unittest.main()
