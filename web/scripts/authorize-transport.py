"""HTTP transport for the real oidc-client-ts integration check.

This does not exchange codes or validate tokens; the installed JS library does
that. A single process keeps the local Keycloak cookie jar for the SSO check.
Input/output are private pipes to the Node check, never terminal logs.
"""
import http.cookiejar
import importlib.util
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("verify_stack", root / "scripts" / "verify-stack.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
password = helpers.configuration()["DEMO_USER_PASSWORD"]
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), helpers.LoopbackHTTPHandler(),
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar(policy=helpers.LoopbackCookiePolicy())),
    helpers.NoRedirect())

for line in sys.stdin:
    try:
        command = json.loads(line)
        url = command["url"]
        assert url.startswith(helpers.ISSUER + "/protocol/openid-connect/auth?"), "Unexpected authorization origin"
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        assert query.get("redirect_uri") in (["http://localhost:3001/"], ["http://localhost:3002/"]), "Unexpected callback"
        status, headers, body = helpers.request(url, opener=opener)
        used_password = False
        if status == 200:
            assert not command["expectSso"], "Second client did not reuse the SSO session"
            form = helpers.LoginForm()
            form.feed(body.decode())
            assert form.action and form.action.startswith(helpers.ISSUER + "/"), "Local login form missing"
            status, headers, _ = helpers.form_post(form.action, {**form.fields, "username": "alice.it", "password": password}, opener)
            used_password = True
        assert status in (302, 303), "Authorization did not return a redirect"
        callback = headers.get("Location", "")
        assert callback.startswith(query["redirect_uri"][0]), "Unexpected redirect destination"
        print(json.dumps({"callback": callback, "usedPassword": used_password}), flush=True)
    except Exception:
        # Never include a URL, code, credentials or response body in logs.
        print(json.dumps({"error": "Local authorization transport failed"}), flush=True)
