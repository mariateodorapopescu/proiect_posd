"""Deterministic tests for batch.py; no Keycloak, API or real sessions."""
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import contextlib
import csv
import io
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import batch
import measure


ISSUER = "http://localhost:8080/realms/securesync"
ACTION = ISSUER + "/login-actions/authenticate?session_code=abc&execution=1"
FORM = ('<html><form id="kc-form-login" action="' + ACTION.replace("&", "&amp;") +
        '" method="post"><input type="hidden" name="credentialId" value="">'
        '<input type="text" name="username"></form></html>')


class Response:
    def __init__(self, status, text="", headers=None, body=None):
        self.status_code, self.text = status, text
        self.headers, self.body = headers or {}, body

    def json(self):
        return self.body


class LoginSession:
    """Plays Keycloak's authorization page, login form and token endpoint."""

    def __init__(self, form=FORM, action_status=302, redirect_state=None, code_count=1):
        self.form, self.action_status = form, action_status
        self.redirect_state, self.code_count = redirect_state, code_count
        self.calls = []
        self.state = self.challenge = None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "GET":
            query = parse_qs(urlsplit(url).query)
            self.state, self.challenge = query["state"][0], query["code_challenge"][0]
            return Response(200, self.form)
        if url.endswith("/token"):
            return Response(200, body={"access_token": "issued-token"})
        state = self.state if self.redirect_state is None else self.redirect_state
        if self.action_status == 200:
            return Response(200, self.form)
        codes = "&code=authorization-code" * self.code_count
        return Response(self.action_status, headers={
            "Location": f"http://localhost:8765/callback?state={state}{codes}"})


def args(**overrides):
    options = dict(issuer=ISSUER, client_id="securesync-experiment", callback_port=8765,
                   request_timeout=1, audience="securesync-api", username="alice.it", guard=5.0)
    options.update(overrides)
    return SimpleNamespace(**options)


def token(iat, exp):
    return "test." + measure.b64url(
        ('{"sub":"u","sid":"s","iss":"%s","aud":["securesync-api"],"iat":%s,"exp":%s}'
         % (ISSUER, iat, exp)).encode()) + ".test"


class LoginTests(unittest.TestCase):
    def test_login_uses_s256_pkce_and_posts_credentials_only_to_the_realm(self):
        session = LoginSession()
        self.assertEqual(batch.form_login_token(session, args(), "alice.it", "demo-secret"), "issued-token")
        get, post, exchange = session.calls
        self.assertTrue(all(call[2]["allow_redirects"] is False for call in session.calls))
        self.assertEqual(post[1], ACTION)
        self.assertEqual(post[2]["data"], {"credentialId": "", "username": "alice.it",
                                           "password": "demo-secret"})
        self.assertTrue(exchange[1].startswith(ISSUER + "/protocol/openid-connect/token"))
        verifier = exchange[2]["data"]["code_verifier"]
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        self.assertEqual(session.challenge, measure.b64url(digest))
        self.assertIn("code_challenge_method=S256", get[1])
        self.assertEqual(parse_qs(urlsplit(get[1]).query)["scope"], ["openid documents:read"])
        self.assertEqual(exchange[2]["data"]["redirect_uri"], "http://localhost:8765/callback")
        self.assertNotIn("demo-secret", get[1] + exchange[1])
        self.assertNotIn("password", exchange[2]["data"])

    def test_keycloak_redirect_to_login_actions_is_followed_inside_the_realm(self):
        class RedirectingSession(LoginSession):
            def request(self, method, url, **kwargs):
                if method == "GET" and "hop=1" not in url:
                    self.calls.append((method, url, kwargs))
                    query = parse_qs(urlsplit(url).query)
                    self.state, self.challenge = query["state"][0], query["code_challenge"][0]
                    return Response(302, headers={"Location": "/realms/securesync/login-actions/authenticate?hop=1"})
                if method == "GET":
                    self.calls.append((method, url, kwargs))
                    return Response(200, self.form)
                return super().request(method, url, **kwargs)
        session = RedirectingSession()
        self.assertEqual(batch.form_login_token(session, args(), "alice.it", "demo-secret"), "issued-token")
        self.assertEqual([call[0] for call in session.calls], ["GET", "GET", "POST", "POST"])
        self.assertTrue(session.calls[1][1].startswith("http://localhost:8080/realms/securesync/login-actions/"))

    def test_redirect_outside_the_realm_or_in_a_loop_is_refused(self):
        class Redirect:
            def __init__(self, location):
                self.location, self.calls = location, []
            def request(self, method, url, **kwargs):
                self.calls.append(method)
                return Response(302, headers={"Location": self.location})
        foreign = Redirect("http://evil.example/steal")
        with self.assertRaises(measure.ExperimentError) as raised:
            batch.form_login_token(foreign, args(), "alice.it", "demo-secret")
        self.assertEqual(str(raised.exception), "login_redirect_outside_realm:evil.example/steal")
        self.assertEqual(foreign.calls, ["GET"], "no password was sent")
        callback = Redirect("http://localhost:8765/callback?error=invalid_scope&state=secret-state&code=abc")
        with self.assertRaises(measure.ExperimentError) as raised:
            batch.form_login_token(callback, args(), "alice.it", "demo-secret")
        self.assertEqual(str(raised.exception),
                         "login_redirect_outside_realm:localhost:8765/callback error=invalid_scope")
        self.assertNotIn("secret-state", str(raised.exception))
        loop = Redirect(ISSUER + "/login-actions/authenticate")
        with self.assertRaises(measure.ExperimentError) as raised:
            batch.form_login_token(loop, args(), "alice.it", "demo-secret")
        self.assertEqual(str(raised.exception), "too_many_login_redirects")
        self.assertEqual(set(loop.calls), {"GET"})

    def test_form_on_another_origin_never_receives_the_password(self):
        session = LoginSession(form=FORM.replace("http://localhost:8080", "http://evil.example"))
        with self.assertRaises(measure.ExperimentError) as raised:
            batch.form_login_token(session, args(), "alice.it", "demo-secret")
        self.assertEqual(str(raised.exception), "login_form_missing_or_foreign_origin")
        self.assertEqual([call[0] for call in session.calls], ["GET"])

    def test_rejection_reports_keycloaks_feedback_text_and_never_the_password(self):
        page = FORM + '<span id="input-error" class="x">Invalid username or password.</span>'
        session = LoginSession(form=page, action_status=200)
        with self.assertRaises(measure.ExperimentError) as raised:
            batch.form_login_token(session, args(), "alice.it", "demo-secret")
        self.assertEqual(str(raised.exception), "login_rejected:http_200 Invalid username or password.")
        self.assertNotIn("demo-secret", str(raised.exception))

    def test_error_page_text_is_reported_for_a_400(self):
        page = ('<html><head><title>Sign in</title></head><body><div id="kc-error-message">'
                '<p class="instruction">Cookie not found. Please make sure cookies are enabled.</p></div></body></html>')
        response = Response(400, page)
        self.assertEqual(batch.login_rejection(response),
                         "login_rejected:http_400 Cookie not found. Please make sure cookies are enabled.")
        self.assertEqual(batch.login_rejection(Response(400, "")), "login_rejected:http_400")

    def test_secure_cookies_are_relaxed_for_loopback_http_and_only_names_are_reported(self):
        import http.cookiejar
        import requests
        jar = requests.cookies.RequestsCookieJar()
        jar.set("KC_RESTART", "secret-value", domain="localhost", path="/realms/securesync/", secure=True)
        session = SimpleNamespace(cookies=jar)
        batch.relax_loopback_cookies(session)
        self.assertFalse(any(cookie.secure for cookie in jar))
        self.assertEqual(batch.cookie_names(session), "KC_RESTART")
        self.assertNotIn("secret-value", batch.cookie_names(session))
        batch.relax_loopback_cookies(LoginSession())  # sessions without a cookie jar are tolerated

    def test_missing_form_is_refused(self):
        with self.assertRaises(measure.ExperimentError):
            batch.form_login_token(LoginSession(form="<html></html>"), args(), "alice.it", "x")

    def test_rejected_login_state_mismatch_and_bad_code_are_refused(self):
        cases = (({"action_status": 200}, "login_rejected:http_200"),
                 ({"redirect_state": "forged"}, "callback_state_mismatch"),
                 ({"code_count": 0}, "authorization_code_missing"),
                 ({"code_count": 2}, "authorization_code_missing"))
        for options, expected in cases:
            with self.subTest(expected=expected, options=options):
                session = LoginSession(**options)
                with self.assertRaises(measure.ExperimentError) as raised:
                    batch.form_login_token(session, args(), "alice.it", "x")
                self.assertEqual(str(raised.exception), expected)
                # The code exchange is never attempted after a refused callback.
                self.assertFalse(any(call[1].endswith("/token") for call in session.calls))

    def test_password_comes_from_environment_or_env_file_only(self):
        with TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("# DEMO_USER_PASSWORD=commented\nOTHER=1\nDEMO_USER_PASSWORD = file-secret \n")
            self.assertEqual(batch.demo_password({"DEMO_USER_PASSWORD": "env-secret"}, env_file), "env-secret")
            self.assertEqual(batch.demo_password({}, env_file), "file-secret")
            with self.assertRaises(measure.ExperimentError):
                batch.demo_password({}, Path(directory) / "missing.env")


class ScheduleTests(unittest.TestCase):
    def test_random_phase_covers_every_bin_once_and_is_reproducible(self):
        first = batch.phase_fractions(10, "random", 7)
        self.assertEqual(first, batch.phase_fractions(10, "random", 7))
        self.assertNotEqual(first, batch.phase_fractions(10, "random", 8))
        self.assertEqual(sorted(int(value * 10) for value in first), list(range(10)))
        self.assertTrue(all(0 <= value < 1 for value in first))

    def test_phase_none_revokes_immediately(self):
        self.assertEqual(batch.phase_fractions(3, "none", 1), [0.0, 0.0, 0.0])

    def run_one(self, fraction, iat=1000, exp=1060, **options):
        events = []

        def login(session, arguments, username, password):
            events.append(("login", username, password))
            return token(iat, exp)

        def admin(session, arguments):
            events.append(("admin",))
            return "admin-token"

        def measured(arguments, user_token, admin_token, session):
            events.append(("measure", admin_token))
            return "result"

        result = batch.run_one(args(**options), fraction, "demo-secret", login=login,
                               sleep=lambda seconds: events.append(("sleep", seconds)),
                               wall_clock=lambda: 1000.0, measure_run=measured, admin_token=admin)
        return result, events

    def test_wait_is_a_fraction_of_the_lifetime_left_after_the_guard(self):
        result, events = self.run_one(0.5)
        self.assertEqual(result, "result")
        self.assertEqual([event[0] for event in events], ["login", "sleep", "admin", "measure"])
        self.assertEqual(events[1][1], 0.5 * (60 - 5))
        self.assertEqual(events[0][1:], ("alice.it", "demo-secret"))

    def test_admin_token_is_requested_after_the_wait(self):
        _result, events = self.run_one(1.0)
        self.assertLess(events.index(("sleep", 55.0)), events.index(("admin",)))

    def test_lifetime_not_longer_than_the_guard_is_a_preparation_error(self):
        with self.assertRaises(measure.ExperimentError) as raised:
            self.run_one(0.5, exp=1004)
        self.assertEqual(str(raised.exception), "token_lifetime_shorter_than_guard")


class MainTests(unittest.TestCase):
    def fake_result(self, outcome="denied"):
        result = measure.RunResult("run-" + outcome, "jwt", "2026-11-22T00:00:00+00:00", outcome=outcome,
                                   time_to_deny_s=1.5 if outcome == "denied" else None,
                                   token_ttl_s=60, remaining_at_revoke_s=30.0)
        samples = [measure.Sample("baseline", 0.0, 0.01, 10.0, 200)]
        return result, samples, 1.0

    def main(self, directory, run, *extra):
        with patch.dict(os.environ, {"DEMO_USER_PASSWORD": "demo-secret"}):
            return batch.main(["--strategy", "jwt", "--runs", "4", "--output", directory, *extra], run)

    def test_every_repetition_is_written_once_even_with_parallel_workers(self):
        threads, fractions = set(), []

        def run(arguments, fraction, password):
            threads.add(threading.get_ident())
            fractions.append(fraction)
            self.assertEqual(password, "demo-secret")
            return self.fake_result()

        with TemporaryDirectory() as directory:
            self.assertEqual(self.main(directory, run, "--workers", "2"), 0)
            with (Path(directory) / "runs.csv").open(newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 4)
            self.assertEqual(sorted(int(value * 4) for value in fractions), [0, 1, 2, 3])
            text = "".join(path.read_text() for path in Path(directory).glob("*.csv"))
            self.assertNotIn("demo-secret", text)

    def test_an_invalid_repetition_gives_exit_code_two(self):
        with TemporaryDirectory() as directory:
            self.assertEqual(self.main(directory, lambda *_: self.fake_result("invalid")), 2)

    def test_a_preparation_error_stops_the_series_without_inventing_results(self):
        def run(arguments, fraction, password):
            raise measure.ExperimentError("login_rejected")

        with TemporaryDirectory() as directory:
            self.assertEqual(self.main(directory, run), 2)
            self.assertFalse((Path(directory) / "runs.csv").exists())

    def test_unsafe_options_are_refused_before_any_login(self):
        def run(*_):
            self.fail("No login may start")

        for extra in (["--keycloak-url", "https://keycloak.example"], ["--workers", "99"],
                      ["--token-file", "token.txt"], ["--confirmations", "4"],
                      ["--endpoint", "/api/documents?x=1"]):
            with self.subTest(extra=extra), TemporaryDirectory() as directory, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.main(directory, run, *extra)

    def test_missing_demo_password_stops_without_a_login(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
                patch.object(batch, "demo_password", side_effect=measure.ExperimentError("missing_DEMO_USER_PASSWORD")):
            self.assertEqual(batch.main(["--strategy", "jwt", "--output", directory],
                                        lambda *_: self.fail("No login may start")), 2)


if __name__ == "__main__":
    unittest.main()
