"""Repeat SecureSync revocation measurements without opening a browser.

Every repetition logs in with a fresh Keycloak session (Authorization Code with S256 PKCE
over loopback HTTP, demo credentials taken only from the local environment), waits for a
stratified random fraction of the token lifetime, and then runs measure.measure_run
unchanged. The random wait varies the token age at revocation, so a locally validated JWT
is not always revoked at the same point of its lifetime.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from html.parser import HTMLParser
import os
from pathlib import Path
import random
import re
import secrets
import sys
import threading
import time
from typing import Callable
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit

import requests

import measure

LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
MAX_WORKERS = 16
MAX_LOGIN_REDIRECTS = 5
REDIRECT_STATUSES = (301, 302, 303, 307, 308)
# Same scopes as the web apps request; this realm defines no "profile" scope (invalid_scope).
LOGIN_SCOPE = "openid documents:read"


class LoginForm(HTMLParser):
    """Collects the Keycloak login form action and its hidden fields."""

    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}
        self.in_form = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "kc-form-login":
            self.action = attrs.get("action")
            self.in_form = True
        if tag == "input" and self.in_form and attrs.get("type") == "hidden" and attrs.get("name"):
            self.fields[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_form = False


def demo_password(environ=None, env_file: Path | None = None) -> str:
    """Read the synthetic demo password from the process environment or the local .env."""
    environ = os.environ if environ is None else environ
    value = environ.get("DEMO_USER_PASSWORD", "")
    if value:
        return value
    env_file = env_file or Path(__file__).resolve().parents[1] / ".env"
    try:
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            key, separator, rest = line.partition("=")
            if separator and not key.lstrip().startswith("#") and key.strip() == "DEMO_USER_PASSWORD":
                return rest.strip()
    except OSError:
        pass
    raise measure.ExperimentError("missing_DEMO_USER_PASSWORD")


def relax_loopback_cookies(session) -> None:
    """Let Keycloak's cookies travel over plain loopback HTTP.

    Keycloak can mark its login cookies Secure; browsers still send them to http://localhost,
    but Python's cookie jar does not, and Keycloak then answers 400 "Restart login cookie not
    found". Only loopback is ever used here (main() refuses any other Keycloak host).
    """
    for cookie in getattr(session, "cookies", ()):
        cookie.secure = False


def cookie_names(session) -> str:
    """Names (never values) of the cookies in the login session, for failure diagnostics."""
    return ",".join(sorted({cookie.name for cookie in getattr(session, "cookies", ())}))


def describe_foreign_redirect(url: str) -> str:
    """Error text for a redirect that leaves the realm: where to, and the OAuth error if any.

    Only the host, the path and the OAuth `error` code are kept; the query may hold state or
    codes, so the rest is never printed.
    """
    parts = urlsplit(url)
    error = parse_qs(parts.query).get("error", [""])[0][:40]
    safe = "".join(c for c in error if c.isalnum() or c in "_-")
    return f"login_redirect_outside_realm:{parts.netloc}{parts.path}" + (f" error={safe}" if safe else "")


def fetch_login_page(session, args, url: str):
    """GET the authorization URL; Keycloak 26 first redirects to login-actions/authenticate.

    Redirects are followed by hand and only inside the configured realm, so cookies and the
    later password POST never leave the Keycloak origin.
    """
    for _ in range(MAX_LOGIN_REDIRECTS + 1):
        page = measure.request(session, "GET", url, args.request_timeout)
        relax_loopback_cookies(session)
        if page.status_code in REDIRECT_STATUSES:
            url = urljoin(url, page.headers.get("Location", ""))
            if not url.startswith(args.issuer + "/"):
                raise measure.ExperimentError(describe_foreign_redirect(url))
            continue
        if page.status_code != 200:
            raise measure.ExperimentError(f"authorization_page_http_{page.status_code}")
        return page
    raise measure.ExperimentError("too_many_login_redirects")


def login_rejection(response) -> str:
    """'login_rejected' plus Keycloak's own feedback line (for example 'Invalid username or password.').

    Only the short text of the error element is kept; the submitted password is never echoed by
    Keycloak and is never part of the message.
    """
    page = getattr(response, "text", "") or ""
    match = re.search(r'(?:id="input-error"|kc-feedback-text)[^>]*>\s*([^<]{1,120}?)\s*<', page)
    if not match:
        # Keycloak error pages (expired action, missing cookie, ...) use kc-error-message.
        block = re.search(r'kc-error-message[^>]*>(.{1,600}?)</div>', page, re.S)
        text = re.sub(r"<[^>]+>", " ", block.group(1)) if block else ""
        title = re.search(r"<title>\s*([^<]{1,80}?)\s*</title>", page)
        match = re.match(r"(.*)", " ".join(text.split())[:120] or (title.group(1) if title else ""))
    detail = " ".join(match.group(1).split()) if match else ""
    detail = "".join(c for c in detail if c.isprintable())
    return f"login_rejected:http_{response.status_code}" + (f" {detail}" if detail else "")


def form_login_token(session, args, username: str, password: str) -> str:
    """Authorization Code + S256 PKCE through the Keycloak login form, no browser."""
    verifier, state = secrets.token_urlsafe(64), secrets.token_urlsafe(32)
    redirect = f"http://localhost:{args.callback_port}/callback"
    challenge = measure.b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    url = f"{args.issuer}/protocol/openid-connect/auth?" + urlencode({
        "client_id": args.client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": LOGIN_SCOPE, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    page = fetch_login_page(session, args, url)
    form = LoginForm()
    form.feed(page.text)
    # Never send the password to an origin other than the configured Keycloak realm.
    if not form.action or not form.action.startswith(args.issuer + "/"):
        raise measure.ExperimentError("login_form_missing_or_foreign_origin")
    relax_loopback_cookies(session)
    response = measure.request(session, "POST", form.action, args.request_timeout,
                               data={**form.fields, "username": username, "password": password})
    if response.status_code not in (302, 303):
        names = cookie_names(session)
        raise measure.ExperimentError(login_rejection(response) + (f" [cookies: {names}]" if names else ""))
    location = response.headers.get("Location", "")
    if not location.startswith(redirect + "?"):
        raise measure.ExperimentError("unexpected_login_redirect")
    query = parse_qs(urlsplit(location).query)
    if query.get("state") != [state]:
        raise measure.ExperimentError("callback_state_mismatch")
    if query.get("error") or len(query.get("code", [])) != 1:
        raise measure.ExperimentError("authorization_code_missing")
    response = measure.request(session, "POST", f"{args.issuer}/protocol/openid-connect/token",
                               args.request_timeout,
                               data={"grant_type": "authorization_code", "client_id": args.client_id,
                                     "code": query["code"][0], "redirect_uri": redirect,
                                     "code_verifier": verifier})
    if response.status_code != 200:
        raise measure.ExperimentError(f"code_exchange_http_{response.status_code}")
    token = measure.response_json(response, "invalid_token_response").get("access_token")
    if not isinstance(token, str) or not token:
        raise measure.ExperimentError("missing_access_token")
    return token


def phase_fractions(runs: int, mode: str, seed: int) -> list[float]:
    """Fractions of the usable token lifetime to wait before revoking.

    random: one uniform draw in each of `runs` equal bins, shuffled, so even a small series
    covers the whole lifetime and the order does not follow the draw. none: revoke at once.
    """
    if mode == "none":
        return [0.0] * runs
    rng = random.Random(seed)
    fractions = [(index + rng.random()) / runs for index in range(runs)]
    rng.shuffle(fractions)
    return fractions


def run_one(args, fraction: float, password: str, *,
            login: Callable = form_login_token, sleep: Callable[[float], None] = time.sleep,
            wall_clock: Callable[[], float] = time.time,
            measure_run: Callable = measure.measure_run,
            admin_token: Callable = measure.admin_access_token):
    """One repetition: fresh login, wait for the chosen token age, then measure."""
    # The login session holds Keycloak cookies; keep them away from API and Admin API calls.
    with requests.Session() as login_session:
        token = login(login_session, args, args.username, password)
    claims = measure.token_metadata(token, args.issuer, args.audience)
    window = claims["exp"] - wall_clock() - args.guard
    if window <= 0:
        raise measure.ExperimentError("token_lifetime_shorter_than_guard")
    sleep(fraction * window)
    with requests.Session() as session:
        # Obtained after the wait: the administrative token lives only as long as a realm token.
        return measure_run(args, token, admin_token(session, args), session)


def parser():
    cli = measure.parser()
    cli.prog = "batch.py"
    cli.description = __doc__
    cli.set_defaults(runs=100)
    cli.add_argument("--username", default="alice.it", help="Synthetic demo user with USER or ADMIN")
    cli.add_argument("--workers", type=measure.positive_int, default=1,
                     help="Parallel repetitions; keep the same value for both strategies")
    cli.add_argument("--seed", type=int, default=2026, help="Seed of the random token-age schedule")
    cli.add_argument("--phase", choices=("random", "none"), default="random",
                     help="random: revoke at a stratified random token age; none: revoke right after login")
    cli.add_argument("--guard", type=measure.positive_float, default=5.0,
                     help="Seconds of token lifetime kept free for baseline requests and revocation")
    return cli


def main(argv=None, run: Callable = run_one):
    cli = parser()
    args = cli.parse_args(argv)
    if not 1 <= args.callback_port <= 65535:
        cli.error("--callback-port must be between 1 and 65535")
    if (not args.endpoint.startswith("/api/") or any(c in args.endpoint for c in ("?", "#", "\\"))
            or ".." in args.endpoint):
        cli.error("--endpoint must be a fixed /api/ path without query or traversal")
    if args.confirmations < 5:
        cli.error("Use at least five consecutive denial responses")
    if args.token_file:
        cli.error("batch.py logs in itself; use measure.py for a supplied token")
    if args.workers > MAX_WORKERS:
        cli.error(f"--workers must be at most {MAX_WORKERS}")
    if urlsplit(args.keycloak_url).hostname not in LOOPBACK_HOSTS:
        cli.error("The demo password is sent only to a loopback Keycloak")
    args.issuer = f"{args.keycloak_url}/realms/{quote(args.realm, safe='')}"
    try:
        password = demo_password()
    except measure.ExperimentError as error:
        print(f"Experiment oprit: {error}", file=sys.stderr)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)
    fractions = phase_fractions(args.runs, args.phase, args.seed)
    lock, counts = threading.Lock(), {}
    print(f"Strategie {args.strategy}; {args.runs} repetări; {args.workers} lucrători; "
          f"faza {args.phase}; seed {args.seed}.")

    def task(index):
        result, samples, revoked_at = run(args, fractions[index], password)
        with lock:
            measure.write_run(args.output, result, samples, revoked_at)
            counts[result.outcome] = counts.get(result.outcome, 0) + 1
            print(f"Repetarea {index + 1}/{args.runs}: {result.outcome}; "
                  f"timp până la refuz: {result.time_to_deny_s}; "
                  f"durată rămasă la revocare: {result.remaining_at_revoke_s}; "
                  f"eroare: {result.error or '-'}", flush=True)

    executor = ThreadPoolExecutor(max_workers=args.workers)
    futures = [executor.submit(task, index) for index in range(args.runs)]
    try:
        for future in as_completed(futures):
            future.result()
    except (measure.ExperimentError, OSError) as error:
        # File/system exceptions may include private paths; keep terminal details generic.
        reason = str(error) if isinstance(error, measure.ExperimentError) else "local_file_error"
        print(f"Experiment oprit: {reason}", file=sys.stderr)
        return 2
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    print("Rezumat: " + ", ".join(f"{name}={count}" for name, count in sorted(counts.items())))
    return 2 if counts.get("invalid") else 0


if __name__ == "__main__":
    raise SystemExit(main())
