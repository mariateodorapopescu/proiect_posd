"""Measure SecureSync session revocation without renewing the tested access token."""
from __future__ import annotations

import argparse
import base64
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import sys
import time
from typing import Callable
from urllib.parse import parse_qs, quote, urlencode, urlsplit
import uuid
import webbrowser

import requests


class ExperimentError(Exception):
    """Safe, token-free error suitable for the terminal and output files."""


@dataclass
class Sample:
    phase: str
    started: float
    completed: float
    latency_ms: float
    status: int


@dataclass
class RunResult:
    run_id: str
    strategy: str
    started_utc: str
    outcome: str = "invalid"
    time_to_deny_s: float | None = None
    observation_s: float = 0.0
    token_ttl_s: int = 0
    remaining_at_revoke_s: float | None = None
    revoke_latency_ms: float | None = None
    interval_s: float = 0.1
    confirmation_count: int = 5
    error: str = ""


RUN_FIELDS = list(RunResult.__dataclass_fields__)
SAMPLE_FIELDS = ["run_id", "strategy", "phase", "offset_s", "latency_ms", "status"]


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def token_metadata(token: str, issuer: str, audience: str) -> dict:
    """Decode experiment metadata, not authentication; the API validates this token."""
    if not token or any(c.isspace() for c in token):
        raise ExperimentError("invalid_token_format")
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError()
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        if not isinstance(claims, dict):
            raise ValueError()
        aud = claims.get("aud", [])
        aud = [aud] if isinstance(aud, str) else aud
        if claims.get("iss") != issuer or not isinstance(aud, list) or audience not in aud:
            raise ValueError()
        if not all(isinstance(claims.get(key), str) and claims[key] for key in ("sub", "sid")):
            raise ValueError()
        for key in ("exp", "iat"):
            if isinstance(claims.get(key), bool) or not isinstance(claims.get(key), (int, float)):
                raise ValueError()
            if not math.isfinite(claims[key]):
                raise ValueError()
        if claims["exp"] <= claims["iat"]:
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ExperimentError("invalid_token_metadata") from None
    return claims


def safe_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise argparse.ArgumentTypeError("Use an HTTP(S) URL without credentials, query or fragment")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise argparse.ArgumentTypeError("Plain HTTP is allowed only on loopback; use HTTPS remotely")
    return value.rstrip("/")


def request(session, method: str, url: str, timeout: float, **kwargs):
    try:
        # Never follow redirects with access tokens or administrative credentials.
        return session.request(method, url, timeout=timeout, allow_redirects=False, **kwargs)
    except requests.RequestException:
        raise ExperimentError("network_error") from None


def response_json(response, error: str) -> dict:
    try:
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise ExperimentError(error) from None


def admin_access_token(session, args) -> str:
    secret = os.environ.get("EXPERIMENT_ADMIN_CLIENT_SECRET", "")
    if not secret:
        raise ExperimentError("missing_EXPERIMENT_ADMIN_CLIENT_SECRET")
    response = request(session, "POST", f"{args.issuer}/protocol/openid-connect/token", args.request_timeout,
                       data={"grant_type": "client_credentials", "client_id": args.admin_client_id,
                             "client_secret": secret})
    if response.status_code != 200:
        raise ExperimentError(f"admin_login_http_{response.status_code}")
    token = response_json(response, "invalid_admin_token_response").get("access_token")
    if not isinstance(token, str) or not token:
        raise ExperimentError("missing_admin_access_token")
    return token


def browser_access_token(session, args) -> str:
    """Authorization Code + S256 PKCE; state and verifier live only in this process."""
    verifier, state = secrets.token_urlsafe(64), secrets.token_urlsafe(32)
    redirect = f"http://localhost:{args.callback_port}/callback"
    received: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # A callback URL contains an authorization code; do not log it.

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            if parsed.path != "/callback" or query.get("state") != [state]:
                self.send_error(400, "Invalid authorization callback")
                return
            if query.get("error"):
                received["error"] = "authorization_denied"
            elif len(query.get("code", [])) == 1:
                received["code"] = query["code"][0]
            else:
                received["error"] = "missing_authorization_code"
            body = b"SecureSync authorization received. You may close this window."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    try:
        server = HTTPServer(("127.0.0.1", args.callback_port), Callback)
    except OSError:
        raise ExperimentError("callback_port_unavailable") from None
    authorization_url = f"{args.issuer}/protocol/openid-connect/auth?" + urlencode({
        "client_id": args.client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": "openid profile documents:read", "state": state,
        "code_challenge": b64url(hashlib.sha256(verifier.encode("ascii")).digest()),
        "code_challenge_method": "S256",
    })
    print("Deschide autentificarea în browser (URL-ul nu conține token-uri):")
    print(authorization_url)
    try:
        server.timeout = 0.5
        webbrowser.open(authorization_url)
        deadline = time.monotonic() + args.login_timeout
        while not received and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if "error" in received:
        raise ExperimentError(received["error"])
    if "code" not in received:
        raise ExperimentError("authorization_timeout")
    response = request(session, "POST", f"{args.issuer}/protocol/openid-connect/token", args.request_timeout,
                       data={"grant_type": "authorization_code", "client_id": args.client_id,
                             "code": received["code"], "redirect_uri": redirect, "code_verifier": verifier})
    if response.status_code != 200:
        raise ExperimentError(f"code_exchange_http_{response.status_code}")
    token = response_json(response, "invalid_token_response").get("access_token")
    if not isinstance(token, str) or not token:
        raise ExperimentError("missing_access_token")
    return token


def measure_run(args, token: str, admin_token: str, session,
                clock: Callable[[], float] = time.monotonic,
                wall_clock: Callable[[], float] = time.time,
                sleep: Callable[[float], None] = time.sleep):
    result = RunResult(uuid.uuid4().hex, args.strategy, datetime.now(timezone.utc).isoformat(),
                       interval_s=args.interval, confirmation_count=args.confirmations)
    samples: list[Sample] = []
    revoked_at = None
    try:
        claims = token_metadata(token, args.issuer, args.audience)
        result.token_ttl_s = int(claims["exp"] - claims["iat"])
        if args.ttl is not None and result.token_ttl_s != args.ttl:
            raise ExperimentError("token_ttl_differs_from_requested_ttl")
        headers = {"Authorization": f"Bearer {token}", "Cache-Control": "no-cache"}
        me = request(session, "GET", f"{args.api_url}/api/me", args.request_timeout, headers=headers)
        if me.status_code != 200:
            raise ExperimentError(f"identity_baseline_http_{me.status_code}")
        identity = response_json(me, "invalid_identity_response")
        if identity.get("strategy") != args.strategy:
            raise ExperimentError("api_strategy_differs_from_requested_strategy")
        if identity.get("sub") != claims["sub"]:
            raise ExperimentError("api_identity_differs_from_token")

        def probe(phase):
            start = clock()
            response = request(session, "GET", f"{args.api_url}{args.endpoint}", args.request_timeout,
                               headers=headers)
            end = clock()
            sample = Sample(phase, start, end, (end - start) * 1000, response.status_code)
            samples.append(sample)
            return sample

        # Baseline status must be 200: an authorization failure is not revocation evidence.
        for _ in range(args.baseline_requests):
            sample = probe("baseline")
            if sample.status != 200:
                raise ExperimentError(f"baseline_http_{sample.status}")
        if claims["exp"] <= wall_clock():
            raise ExperimentError("token_expired_before_revocation")
        revoke_start = clock()
        response = request(session, "DELETE",
                           f"{args.keycloak_url}/admin/realms/{quote(args.realm, safe='')}/sessions/"
                           f"{quote(claims['sid'], safe='')}?isOffline=false", args.request_timeout,
                           headers={"Authorization": f"Bearer {admin_token}"})
        revoked_at = clock()
        result.revoke_latency_ms = (revoked_at - revoke_start) * 1000
        if response.status_code != 204:
            revoked_at = None
            raise ExperimentError(f"revocation_http_{response.status_code}")
        result.remaining_at_revoke_s = max(0.0, claims["exp"] - wall_clock())
        if result.remaining_at_revoke_s <= 0:
            raise ExperimentError("token_expired_during_revocation")
        deadline = revoked_at + args.max_wait
        streak, first_deny = 0, None
        while clock() < deadline:
            sample = probe("after_revocation")
            result.observation_s = sample.completed - revoked_at
            if sample.status not in (200, 401, 403):
                raise ExperimentError(f"probe_http_{sample.status}")
            if sample.completed > deadline:
                # A request can start inside the window and finish after it.
                # Keep its raw latency, but do not extend the configured window.
                result.outcome = "censored"
                result.error = "no_confirmed_denial_before_timeout"
                break
            if sample.status in (401, 403):
                if streak == 0:
                    first_deny = sample.completed - revoked_at
                streak += 1
                if streak >= args.confirmations:
                    result.outcome = "denied"
                    result.time_to_deny_s = first_deny
                    break
            elif sample.status == 200:
                streak, first_deny = 0, None
            sleep(min(args.interval, max(0.0, deadline - clock())))
        else:
            result.outcome = "censored"
            result.error = "no_confirmed_denial_before_timeout"
    except ExperimentError as error:
        result.outcome = "invalid"
        result.error = str(error)
        if revoked_at is not None:
            result.observation_s = clock() - revoked_at
    return result, samples, revoked_at


def append_csv(path: Path, fields: list[str], rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists() or path.stat().st_size == 0
    if not new_file:
        with path.open(encoding="utf-8", newline="") as existing:
            if next(csv.reader(existing), None) != fields:
                raise ExperimentError("existing_csv_schema_mismatch")
    with path.open("a", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def write_run(directory: Path, result, samples, revoked_at):
    # Write samples before summary; an interruption can leave incomplete samples but never invented results.
    append_csv(directory / "samples.csv", SAMPLE_FIELDS, [{
        "run_id": result.run_id, "strategy": result.strategy, "phase": s.phase,
        "offset_s": "" if revoked_at is None else round(s.completed - revoked_at, 9),
        "latency_ms": round(s.latency_ms, 6), "status": s.status,
    } for s in samples])
    append_csv(directory / "runs.csv", RUN_FIELDS, [asdict(result)])


def positive_float(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Value must be positive and finite")
    return number


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Value must be positive")
    return number


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--strategy", required=True, choices=("jwt", "introspection"))
    cli.add_argument("--api-url", type=safe_base_url, default="http://localhost:8081")
    cli.add_argument("--keycloak-url", type=safe_base_url, default="http://localhost:8080")
    cli.add_argument("--realm", default="securesync")
    cli.add_argument("--audience", default="securesync-api")
    cli.add_argument("--client-id", default="securesync-experiment")
    cli.add_argument("--admin-client-id", default="securesync-experiment-admin")
    cli.add_argument("--callback-port", type=positive_int, default=8765)
    cli.add_argument("--runs", type=positive_int, default=1)
    cli.add_argument("--ttl", type=positive_int, help="Check observed token TTL; does not change Keycloak")
    cli.add_argument("--baseline-requests", type=positive_int, default=10)
    cli.add_argument("--interval", type=positive_float, default=0.1)
    cli.add_argument("--max-wait", type=positive_float, default=90)
    cli.add_argument("--request-timeout", type=positive_float, default=5)
    cli.add_argument("--login-timeout", type=positive_float, default=180)
    cli.add_argument("--confirmations", type=positive_int, default=5)
    cli.add_argument("--endpoint", default="/api/documents")
    cli.add_argument("--token-file", type=Path, help="Single-run access token file, kept outside the repository")
    cli.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "data")
    return cli


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    if not 1 <= args.callback_port <= 65535:
        cli.error("--callback-port must be between 1 and 65535")
    if (not args.endpoint.startswith("/api/") or any(c in args.endpoint for c in ("?", "#", "\\"))
            or ".." in args.endpoint):
        cli.error("--endpoint must be a fixed /api/ path without query or traversal")
    if args.confirmations < 5:
        cli.error("Use at least five consecutive denial responses")
    env_token = os.environ.get("SECURESYNC_ACCESS_TOKEN", "").strip()
    if (args.token_file or env_token) and args.runs != 1:
        cli.error("A supplied access token supports one run; use browser PKCE for fresh sessions")
    if args.token_file and env_token:
        cli.error("Choose either --token-file or SECURESYNC_ACCESS_TOKEN")
    args.issuer = f"{args.keycloak_url}/realms/{quote(args.realm, safe='')}"
    args.output.mkdir(parents=True, exist_ok=True)
    # Authorization is explicit per request; no access tokens are stored in session defaults.
    invalid_count = 0
    with requests.Session() as session:
        for run_index in range(args.runs):
            print(f"Repetarea {run_index + 1}/{args.runs}; strategie {args.strategy}.")
            try:
                admin_token = admin_access_token(session, args)
                if args.token_file:
                    token = args.token_file.read_text(encoding="utf-8").strip()
                else:
                    token = env_token or browser_access_token(session, args)
                result, samples, revoked_at = measure_run(args, token, admin_token, session)
                write_run(args.output, result, samples, revoked_at)
                print(f"Rezultat: {result.outcome}; primul refuz confirmat: {result.time_to_deny_s}; "
                      f"cereri: {len(samples)}; eroare: {result.error or '-'}")
                invalid_count += result.outcome == "invalid"
            except (ExperimentError, OSError) as error:
                # File/system exceptions may include private paths; keep terminal details generic.
                reason = str(error) if isinstance(error, ExperimentError) else "local_file_or_callback_error"
                print(f"Experiment oprit: {reason}", file=sys.stderr)
                return 2
    return 2 if invalid_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
