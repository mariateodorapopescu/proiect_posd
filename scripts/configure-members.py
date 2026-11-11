"""Add the members feature to an existing local SecureSync realm without resetting data.

Only run against this local demo. Reads bootstrap credentials from .env, never
prints them, and never overwrites an existing member's roles or password.
New installations already import the same configuration from realm-export.json.
"""
import argparse
import copy
import importlib
import json
from pathlib import Path
import secrets
import sys
import urllib.request
from urllib.parse import quote, urlsplit

transport = importlib.import_module("verify-stack")
ROOT = Path(__file__).resolve().parents[1]


def check(response, expected, operation):
    status, _, body = response
    if status not in expected:
        raise RuntimeError(f"{operation} failed (HTTP {status}); no credentials were logged")
    return json.loads(body) if body else None


def configure(keycloak_url):
    local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        transport.LoopbackHTTPHandler(), transport.NoRedirect())
    env_path = ROOT / ".env"
    if not env_path.is_file():
        raise RuntimeError("Run scripts/init-env.ps1 before configuring the local realm")
    env_text = env_path.read_text(encoding="utf-8-sig")
    env = transport.configuration()
    if not env.get("MEMBER_ADMIN_CLIENT_SECRET"):
        env["MEMBER_ADMIN_CLIENT_SECRET"] = secrets.token_urlsafe(32)
        lines = env_text.splitlines()
        lines = [line for line in lines if not line.startswith("MEMBER_ADMIN_CLIENT_SECRET=")]
        lines.append("MEMBER_ADMIN_CLIENT_SECRET=" + env["MEMBER_ADMIN_CLIENT_SECRET"])
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("Added the missing local member-service secret to .env; existing credentials preserved")

    token = check(transport.form_post(keycloak_url + "/realms/master/protocol/openid-connect/token", {
        "grant_type": "password", "client_id": "admin-cli", "username": env["KEYCLOAK_ADMIN"],
        "password": env["KEYCLOAK_ADMIN_PASSWORD"]}, opener=local_http), {200}, "Local bootstrap login")["access_token"]
    admin_url = keycloak_url + "/admin/realms/securesync"

    def kc(path, method="GET", value=None, expected=(200,)):
        headers = {"Authorization": "Bearer " + token}
        data = None
        if value is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(value).encode()
        return check(transport.request(admin_url + path, method=method, data=data, headers=headers, opener=local_http),
                     set(expected), "Realm configuration " + method)

    export = json.loads((ROOT / "keycloak" / "realm-export.json").read_text(encoding="utf-8"))
    role_names = {role["name"] for role in kc("/roles")}
    for role in export["roles"]["realm"]:
        if role["name"] == "IMPLEMENTATOR" and role["name"] not in role_names:
            kc("/roles", "POST", role, (201,))

    scope = next(scope for scope in export["clientScopes"] if scope["name"] == "members:manage")
    existing_scopes = kc("/client-scopes")
    if not any(item["name"] == scope["name"] for item in existing_scopes):
        kc("/client-scopes", "POST", scope, (201,))
        existing_scopes = kc("/client-scopes")
    scope_id = next(item["id"] for item in existing_scopes if item["name"] == "members:manage")
    portal = kc("/clients?clientId=securesync-portal")
    if len(portal) != 1:
        raise RuntimeError("Expected exactly one local Portal client")
    kc("/clients/" + portal[0]["id"] + "/optional-client-scopes/" + scope_id, "PUT", expected=(204,))

    service = copy.deepcopy(next(client for client in export["clients"] if client["clientId"] == "securesync-member-admin"))
    service["secret"] = env["MEMBER_ADMIN_CLIENT_SECRET"]
    existing_service = kc("/clients?clientId=securesync-member-admin")
    if not existing_service:
        kc("/clients", "POST", service, (201,))
        existing_service = kc("/clients?clientId=securesync-member-admin")
    elif len(existing_service) == 1:
        # This named technical client belongs to this setup; do not touch other clients.
        current = existing_service[0]
        current.update({key: value for key, value in service.items()
                        if key not in ("defaultClientScopes", "optionalClientScopes")})
        kc("/clients/" + current["id"], "PUT", current, (204,))
    if len(existing_service) != 1:
        raise RuntimeError("Expected exactly one dedicated member-service client")
    service_id = existing_service[0]["id"]
    admin_scope_id = next(item["id"] for item in existing_scopes if item["name"] == "kc-admin-api")
    kc("/clients/" + service_id + "/default-client-scopes/" + admin_scope_id, "PUT", expected=(204,))
    service_user = kc("/clients/" + service_id + "/service-account-user")
    realm_management = kc("/clients?clientId=realm-management")[0]["id"]
    mapping_path = "/users/" + service_user["id"] + "/role-mappings/clients/" + realm_management
    current_roles = {role["name"] for role in kc(mapping_path)}
    additions = [kc("/clients/" + realm_management + "/roles/" + role)
                 for role in ("manage-users", "view-users", "view-realm") if role not in current_roles]
    if additions:
        kc(mapping_path, "POST", additions, (204,))

    implementator = kc("/users?username=implementator.demo&exact=true")
    if not implementator:
        user = copy.deepcopy(next(user for user in export["users"] if user["username"] == "implementator.demo"))
        user.pop("realmRoles", None)
        for credential in user.get("credentials", []):
            credential["value"] = env["DEMO_USER_PASSWORD"]
        kc("/users", "POST", user, (201,))
        created = kc("/users?username=implementator.demo&exact=true")[0]
        roles = [kc("/roles/" + role) for role in ("USER", "IMPLEMENTATOR")]
        kc("/users/" + quote(created["id"], safe="") + "/role-mappings/realm", "POST", roles, (204,))
        print("Created implementator.demo with USER and IMPLEMENTATOR; demo password read from .env")
    else:
        print("Existing implementator.demo account preserved, including its current roles and password")
    print("Members feature configured. Rebuild/recreate API and Portal to load the feature; PDF data unchanged.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keycloak-url", default="http://localhost:8080")
    args = parser.parse_args()
    url = urlsplit(args.keycloak_url)
    if (url.scheme != "http" or url.hostname not in ("localhost", "127.0.0.1")
            or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment):
        parser.error("Only the local HTTP demo Keycloak origin is supported")
    try:
        configure(args.keycloak_url.rstrip("/"))
    except (RuntimeError, OSError, KeyError, StopIteration, ValueError):
        print("Local members setup failed. Verify Docker, the securesync realm and bootstrap credentials in .env.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
