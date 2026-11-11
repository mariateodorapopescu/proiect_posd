"""Verify the local members feature with real PKCE tokens and disposable fixtures.

Only localhost SecureSync is supported. Bootstrap credentials remain in memory;
no token/password is printed. Existing members are never modified. The uniquely
named test account is deleted in finally, including when a check fails.
"""
import argparse
import base64
import importlib
import json
from pathlib import Path
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
import uuid

transport = importlib.import_module("verify-stack")
ROOT = Path(__file__).resolve().parents[1]
API = "http://localhost:8081"
KEYCLOAK = "http://localhost:8080"
REALM_ADMIN = KEYCLOAK + "/admin/realms/securesync"
FULL_SCOPES = "openid documents:read documents:write members:manage"


class VerificationFailure(Exception):
    """Messages contain only a fixed check label and an HTTP status."""


class Verification:
    def __init__(self, strategy):
        self.strategy = strategy
        self.env = transport.configuration()
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            transport.LoopbackHTTPHandler(), transport.NoRedirect())
        self.lines = []
        self.passed = 0
        self.created = []
        self.bootstrap_token = None

    def record(self, message):
        self.lines.append(message)
        print(message, flush=True)

    def require(self, condition, label):
        if not condition:
            raise VerificationFailure(label)
        self.passed += 1
        self.record("PASS " + label)

    def expect(self, status, response, label):
        actual, _, body = response
        if actual != status:
            raise VerificationFailure(f"{label}: expected HTTP {status}, received {actual}")
        self.passed += 1
        self.record(f"PASS {label} (HTTP {status})")
        return json.loads(body) if body else None

    def api(self, path, token=None, method="GET", value=None):
        if not path.startswith("/api/"):
            raise VerificationFailure("API path is outside the local test namespace")
        headers = {}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = None
        if value is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(value).encode()
        return transport.request(API + path, method=method, data=data, headers=headers, opener=self.http)

    def login(self, username, password=None, scopes=FULL_SCOPES):
        return transport.login(username, password or self.env["DEMO_USER_PASSWORD"], scopes=scopes,
            client_id="securesync-portal", redirect_uri="http://localhost:3002/")[0]

    def claims(self, token):
        # Used only to inspect metadata after the real API has accepted the token.
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))

    def admin(self, path, method="GET", value=None, expected=(200,)):
        if self.bootstrap_token is None:
            response = transport.form_post(KEYCLOAK + "/realms/master/protocol/openid-connect/token", {
                "grant_type": "password", "client_id": "admin-cli", "username": self.env["KEYCLOAK_ADMIN"],
                "password": self.env["KEYCLOAK_ADMIN_PASSWORD"]}, opener=self.http)
            if response[0] != 200:
                raise VerificationFailure("Local fixture setup could not authenticate bootstrap admin")
            self.bootstrap_token = json.loads(response[2])["access_token"]
        headers = {"Authorization": "Bearer " + self.bootstrap_token}
        data = None
        if value is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(value).encode()
        response = transport.request(REALM_ADMIN + path, method=method, data=data, headers=headers, opener=self.http)
        if response[0] not in expected:
            raise VerificationFailure(f"Local fixture operation {method} failed (HTTP {response[0]})")
        return response

    def wait_ready(self):
        deadline = time.monotonic() + 45
        while True:
            try:
                status, _, body = self.api("/api/health")
                if status == 200:
                    self.require(json.loads(body).get("strategy") == self.strategy,
                                 "API strategy matches requested verification")
                    return
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise VerificationFailure("Local API did not become ready within 45 seconds")
            time.sleep(0.5)

    def create_fixture(self):
        username = "verify-members-" + secrets.token_hex(8)
        before = self.admin("/users?username=" + username + "&exact=true")
        if json.loads(before[2]):
            raise VerificationFailure("Disposable fixture name unexpectedly already exists")
        password = secrets.token_urlsafe(32)
        profile = {"username": username, "enabled": True, "emailVerified": True,
            "firstName": "Verification", "lastName": "Fixture", "email": username + "@securesync.test",
            "attributes": {"department": ["HR"]}, "requiredActions": [],
            "credentials": [{"type": "password", "value": password, "temporary": False}]}
        response = self.admin("/users", "POST", profile, (201,))
        location = response[1].get("Location", "")
        user_id = urllib.parse.urlsplit(location).path.rsplit("/", 1)[-1]
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", user_id):
            # A 201 belongs to this new unique account; find its id for cleanup.
            matches = json.loads(self.admin("/users?username=" + username + "&exact=true")[2])
            if len(matches) != 1:
                raise VerificationFailure("Created fixture could not be located for cleanup")
            user_id = matches[0]["id"]
        if str(uuid.UUID(user_id)) != user_id.lower():
            raise VerificationFailure("Unexpected fixture identity format")
        self.created.append((user_id, username))
        role = json.loads(self.admin("/roles/USER")[2])
        self.admin("/users/" + user_id + "/role-mappings/realm", "POST", [role], (204,))
        self.record("Created one disposable local fixture")
        return user_id, username, password, profile

    def run(self):
        self.wait_ready()
        self.expect(401, self.api("/api/members"), "member list without bearer token")
        for username, label in (("alice.it", "USER"), ("admin.demo", "ADMIN")):
            token = self.login(username)
            self.expect(403, self.api("/api/members", token), label + " cannot administer members")
        without_scope = self.login("implementator.demo", scopes="openid documents:read documents:write")
        self.expect(403, self.api("/api/members", without_scope), "IMPLEMENTATOR needs management scope")
        implementator = self.login("implementator.demo")
        identity = self.expect(200, self.api("/api/me", implementator), "implementator identity")
        page = self.expect(200, self.api("/api/members", implementator), "IMPLEMENTATOR member list")
        self.require(len(page["members"]) <= 20 and page["page"] == 0,
                     "member list is bounded and exposes expected pagination")
        self.require(all(not item["username"].startswith("service-account-") for item in page["members"]),
                     "service accounts are absent from member list")
        self.expect(403, self.api("/api/members/" + identity["sub"] + "/access", implementator, "PUT",
                    {"roles": ["USER"], "department": "IT"}), "implementator cannot modify own access")

        target, username, password, original = self.create_fixture()
        access_path = "/api/members/" + target + "/access"
        for value, label in (({"roles": ["realm-admin"], "department": "IT"}, "arbitrary role rejected"),
                ({"roles": ["USER"], "department": "EXECUTIVE"}, "unknown department rejected"),
                ({"roles": [], "department": "IT"}, "empty role set rejected")):
            self.expect(400, self.api(access_path, implementator, "PUT", value), label)
        self.expect(400, self.api("/api/members/not-a-uuid/access", implementator, "PUT",
                    {"roles": ["USER"], "department": "IT"}), "invalid member identifier rejected")
        self.expect(400, self.api("/api/members?page=-1", implementator), "negative member page rejected")
        changed = self.expect(200, self.api(access_path, implementator, "PUT",
                    {"roles": ["USER", "ADMIN"], "department": "IT"}), "grant ADMIN and change department")
        self.require(set(changed["roles"]) == {"USER", "ADMIN"} and changed["department"] == "IT",
                     "saved response reflects effective roles and department")
        fresh = self.login(username, password)
        current = self.expect(200, self.api("/api/me", fresh), "updated fixture authenticates through PKCE")
        managed_roles = set(current["roles"]) & {"USER", "ADMIN", "IMPLEMENTATOR"}
        self.require(managed_roles == {"USER", "ADMIN"} and current["department"] == "IT",
                     "fresh token carries updated ADMIN role and IT department")
        self.expect(200, self.api("/api/documents", fresh), "updated document role is accepted")
        persisted = json.loads(self.admin("/users/" + target)[2])
        self.require(all(persisted.get(key) == original[key] for key in
                         ("firstName", "lastName", "email", "enabled", "emailVerified", "requiredActions")),
                     "role update preserves unrelated profile fields")

        self.expect(200, self.api(access_path, implementator, "PUT",
                    {"roles": ["IMPLEMENTATOR"], "department": "HR"}), "grant IMPLEMENTATOR without document roles")
        temporary_implementator = self.login(username, password)
        self.expect(200, self.api("/api/members", temporary_implementator), "new IMPLEMENTATOR can administer members")
        self.expect(403, self.api("/api/documents", temporary_implementator),
                    "IMPLEMENTATOR alone does not inherit document access")
        self.require(self.claims(temporary_implementator)["exp"] > time.time() + 15,
                     "stale-role test starts before access-token expiry")
        role = json.loads(self.admin("/roles/IMPLEMENTATOR")[2])
        self.admin("/users/" + target + "/role-mappings/realm", "DELETE", [role], (204,))
        self.expect(403, self.api("/api/members", temporary_implementator),
                    "live role check denies removed IMPLEMENTATOR despite unexpired token")

    def cleanup(self):
        failed = False
        for user_id, username in reversed(self.created):
            try:
                response = self.admin("/users/" + user_id, expected=(200, 404))
                if response[0] == 404:
                    continue
                if json.loads(response[2]).get("username") != username or not username.startswith("verify-members-"):
                    raise VerificationFailure("Cleanup identity does not belong to this test")
                self.admin("/users/" + user_id, "DELETE", expected=(204,))
                self.record("Removed disposable local fixture")
            except Exception:
                failed = True
                self.record("FAIL temporary fixture cleanup; inspect only verify-members-* test accounts")
        return not failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=("jwt", "introspection"), default="jwt")
    args = parser.parse_args()
    verification = None
    success = False
    try:
        verification = Verification(args.strategy)
        verification.run()
        success = True
    except VerificationFailure as failure:
        if verification:
            verification.record("FAIL " + str(failure))
        else:
            print("FAIL local verification configuration", flush=True)
    except Exception as failure:
        # Do not print upstream bodies, credentials, redirect codes, or tracebacks.
        message = "FAIL local verification stopped (" + type(failure).__name__ + ")"
        verification.record(message) if verification else print(message, flush=True)
    finally:
        if verification:
            success = verification.cleanup() and success
            verification.record(f"Result: {'PASS' if success else 'FAIL'}; strategy={args.strategy}; checks={verification.passed}")
            output = ROOT / ".local" / ("members-api-verification-" + args.strategy + ".log")
            output.parent.mkdir(exist_ok=True)
            output.write_text("\n".join(verification.lines) + "\n", encoding="utf-8")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
