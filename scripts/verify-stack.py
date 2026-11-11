"""Local integration checks using real Authorization Code + PKCE, never password grant.

Reads only this demo's .env. Credentials/tokens are never printed or written.
Run against the disposable SecureSync demo, not a shared/production realm.
"""
import argparse
import base64
import hashlib
import http.client
import http.cookiejar
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ISSUER = "http://localhost:8080/realms/securesync"
API = "http://localhost:8081"


class LoopbackConnection(http.client.HTTPConnection):
    def connect(self):
        # Docker publishes IPv4 loopback. Keep the OAuth URL/Host/cookie origin
        # unchanged while avoiding slow IPv6 fallback on Windows.
        original = self.host
        if self.host == "localhost":
            self.host = "127.0.0.1"
        try:
            super().connect()
        finally:
            self.host = original


class LoopbackHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, request):
        return self.do_open(LoopbackConnection, request)


LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}), LoopbackHTTPHandler())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LoopbackCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    def return_ok_secure(self, cookie, request):
        # Browsers treat http://localhost as trustworthy. urllib otherwise drops
        # Keycloak's Secure cookies, preventing this local-only protocol test.
        if urllib.parse.urlsplit(request.full_url).hostname == "localhost":
            return True
        return super().return_ok_secure(cookie, request)


class LoginForm(HTMLParser):
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


def request(url, *, method="GET", data=None, headers=None, opener=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        response = (opener or LOCAL_HTTP).open(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


def form_post(url, fields, opener=None):
    return request(url, method="POST", data=urllib.parse.urlencode(fields).encode(),
                   headers={"Content-Type": "application/x-www-form-urlencoded"}, opener=opener)


def login(username, password, scopes="openid documents:read documents:write", *, opener=None,
          client_id="securesync-documente", redirect_uri="http://localhost:3001/", require_sso=False):
    opener = opener or urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        LoopbackHTTPHandler(),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar(policy=LoopbackCookiePolicy())), NoRedirect())
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    params = {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code",
              "scope": scopes, "state": state, "nonce": secrets.token_urlsafe(24),
              "code_challenge": challenge, "code_challenge_method": "S256"}
    status, headers, body = request(ISSUER + "/protocol/openid-connect/auth?" + urllib.parse.urlencode(params), opener=opener)
    if status == 200 and not require_sso:
        form = LoginForm()
        form.feed(body.decode())
        if not form.action or not form.action.startswith(ISSUER + "/"):
            raise AssertionError("Keycloak login form missing or outside local realm")
        status, headers, _ = form_post(form.action, {**form.fields, "username": username, "password": password}, opener)
    assert status in (302, 303), f"PKCE login/SSO failed (HTTP {status})"
    location = headers.get("Location", "")
    assert location.startswith(redirect_uri), "Unexpected authorization redirect"
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(location).query)
    assert query.get("state") == [state] and "code" in query, "Authorization state/code mismatch"
    status, _, body = form_post(ISSUER + "/protocol/openid-connect/token", {
        "grant_type": "authorization_code", "client_id": client_id, "redirect_uri": redirect_uri,
        "code": query["code"][0], "code_verifier": verifier}, opener)
    assert status == 200, f"Code exchange failed (HTTP {status})"
    return json.loads(body)["access_token"], opener


def api(path, token=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = "Bearer " + token
    return request(API + path, headers=headers, **kwargs)


def expect(status, result, label):
    actual = result[0]
    assert actual == status, f"{label}: expected HTTP {status}, received {actual}"
    print(f"PASS {label} ({status})")
    return result[2]


def sample_pdf():
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >>",
               b"<< /Length 0 >>\nstream\n\nendstream"]
    data = b"%PDF-1.4\n"
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 5\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    data += f"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return data


def upload(token, content):
    boundary = "securesync" + secrets.token_hex(16)
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"title\"\r\n\r\n"
            f"Verificare integrare\r\n--{boundary}\r\n"
            "Content-Disposition: form-data; name=\"file\"; filename=\"test.pdf\"\r\n"
            "Content-Type: application/pdf\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return api("/api/documents", token, method="POST", data=body,
               headers={"Content-Type": "multipart/form-data; boundary=" + boundary})


def configuration():
    env_file = Path(__file__).resolve().parents[1] / ".env"
    return dict(line.split("=", 1) for line in env_file.read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.startswith("#") and "=" in line)


def revoke(token, config):
    status, _, body = form_post(ISSUER + "/protocol/openid-connect/token", {
        "grant_type": "client_credentials", "client_id": "securesync-experiment-admin",
        "client_secret": config["EXPERIMENT_ADMIN_CLIENT_SECRET"]})
    assert status == 200, f"Admin client credentials rejected ({status})"
    admin_token = json.loads(body)["access_token"]
    # Claims select this test's session only; actual authorization remains at Keycloak/API.
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    sid = urllib.parse.quote(claims["sid"], safe="")
    result = request("http://localhost:8080/admin/realms/securesync/sessions/" + sid + "?isOffline=false",
                     method="DELETE", headers={"Authorization": "Bearer " + admin_token})
    expect(204, result, "revoke exact test session")
    return time.monotonic()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=("jwt", "introspection"), required=True)
    parser.add_argument("--check-revocation", action="store_true")
    args = parser.parse_args()
    config = configuration()
    password = config["DEMO_USER_PASSWORD"]
    expect(200, api("/api/health"), "public health")
    expect(401, api("/api/documents"), "missing token")
    expect(401, api("/api/documents", "invalid"), "invalid token")
    alice, browser = login("alice.it", password)
    identity = json.loads(expect(200, api("/api/me", alice), "authenticated identity"))
    assert identity["strategy"] == args.strategy, "API strategy differs from test argument"
    assert identity["department"] == "IT", "department claim missing"
    portal, _ = login(None, None, opener=browser, client_id="securesync-portal",
                      redirect_uri="http://localhost:3002/", require_sso=True)
    portal_identity = json.loads(expect(200, api("/api/me", portal), "second client SSO without credentials"))
    assert portal_identity["sub"] == identity["sub"], "SSO identity differs"
    tokens = {name: login(name, password)[0] for name in ("bob.hr", "carol.it", "admin.demo", "observer.it")}
    no_scope, _ = login("alice.it", password, scopes="openid")
    expect(403, api("/api/documents", no_scope), "missing read scope")
    expect(403, api("/api/documents", tokens["observer.it"]), "missing USER/ADMIN role")
    alice, _ = login("alice.it", password)
    expect(400, upload(alice, b"This is not a PDF"), "reject forged PDF content")
    document = json.loads(expect(200, upload(alice, sample_pdf()), "PDF upload"))
    document_id = document["id"]
    try:
        path = f"/api/documents/{document_id}/download"
        expect(401, api(path), "download without token")
        expect(403, api(path, tokens["bob.hr"]), "other department download denied")
        for name, token in (("owner", alice), ("same department", tokens["carol.it"]), ("ADMIN", tokens["admin.demo"])):
            content = expect(200, api(path, token), name + " download")
            assert content == sample_pdf(), "Downloaded bytes differ"
        for name, token, visible in (("owner", alice, True), ("same department", tokens["carol.it"], True),
                                     ("other department", tokens["bob.hr"], False), ("ADMIN", tokens["admin.demo"], True)):
            documents = json.loads(expect(200, api("/api/documents", token), name + " list"))
            assert any(item["id"] == document_id for item in documents) is visible, "List visibility mismatch"
        expect(403, api(f"/api/documents/{document_id}", tokens["bob.hr"], method="DELETE"), "foreign delete denied")
        expect(403, api(f"/api/documents/{document_id}", tokens["carol.it"], method="DELETE"), "department delete denied")
        expect(401, api("/files/" + str(document_id) + ".pdf"), "no public PDF route")
    finally:
        expect(204, api(f"/api/documents/{document_id}", alice, method="DELETE"), "owner cleanup")
    if args.check_revocation:
        alice, _ = login("alice.it", password)
        revoked_at = revoke(alice, config)
        if args.strategy == "jwt":
            expect(200, api("/api/documents", alice), "JWT still accepted immediately after session revoke")
        consecutive = 0
        first_deny = None
        while time.monotonic() - revoked_at < 75 and consecutive < 5:
            status, _, _ = api("/api/documents", alice)
            if status in (401, 403):
                if consecutive == 0:
                    first_deny = time.monotonic() - revoked_at
                consecutive += 1
            elif status == 200:
                consecutive, first_deny = 0, None
            else:
                raise AssertionError(f"Revocation probe failed ({status})")
            time.sleep(0.1)
        assert consecutive == 5, "No sustained access denial within 75s"
        if args.strategy == "introspection":
            assert first_deny < 5, "Introspection revocation unexpectedly slow"
        print(f"PASS sustained revocation denial: strategy={args.strategy}, time-to-deny={first_deny:.3f}s")
    print("All local stack checks passed. Test document deleted.")


if __name__ == "__main__":
    main()
