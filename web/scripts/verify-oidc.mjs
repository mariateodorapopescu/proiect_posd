import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { setDefaultResultOrder } from 'node:dns';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { InMemoryWebStorage, OidcClient, UserManager } from 'oidc-client-ts';
import { createOidcSettings, createSigninArgs } from '../shared/oidc-settings.mjs';

// Direct local HTTP/library integration only; no browser or UI emulation.
// The Python helper handles cookies/forms; all OAuth state, PKCE, code exchange,
// callback validation and user storage are handled by the actual JS library.
setDefaultResultOrder('ipv4first');
const helper = spawn(process.env.PYTHON || 'python', [fileURLToPath(new URL('./authorize-transport.py', import.meta.url))], { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
const responses = createInterface({ input: helper.stdout })[Symbol.asyncIterator]();
const managers = [];
let stage = 'starting the local transport';
helper.stderr.on('data', () => {}); // A traceback may expose OAuth response data.
let transportFailed = false;
helper.on('error', () => { transportFailed = true; });
helper.stdin.on('error', () => { transportFailed = true; });
async function authorize(url, expectSso) {
  assert(!transportFailed, 'Local Python transport is unavailable');
  helper.stdin.write(JSON.stringify({ url, expectSso }) + '\n');
  const next = await Promise.race([
    responses.next(),
    new Promise((_, reject) => { const timeout = setTimeout(() => reject(new Error('Local authorization timed out')), 45000); timeout.unref(); })
  ]);
  assert(!next.done, 'Local authorization transport ended');
  const value = JSON.parse(next.value);
  assert(!value.error, 'Local authorization transport failed');
  return value;
}
const decode = token => JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'));

try {
  let expectedSubject;
  for (const [index, app] of ['documente', 'portal'].entries()) {
    stage = `${app}: creating the library authorization request`;
    const transactionStorage = new InMemoryWebStorage();
    const config = { authority: 'http://localhost:8080/realms/securesync', clientId: `securesync-${app}`, redirectUri: `http://localhost:${3001 + index}/` };
    const settings = createOidcSettings(config, transactionStorage);
    const protocolClient = new OidcClient(settings);
    const signin = createSigninArgs();
    const request = await protocolClient.createSigninRequest({ ...signin, request_type: 'si:r' });
    const url = new URL(request.url);
    assert(url.searchParams.get('code_challenge_method') === 'S256', 'Missing S256 PKCE');
    assert(url.searchParams.get('nonce') === signin.nonce, 'Missing authorization nonce');
    assert(url.searchParams.get('scope') === settings.scope, 'Unexpected requested scopes');
    assert(url.searchParams.get('state'), 'Missing authorization state');

    stage = `${app}: authenticating through local Keycloak HTTP`;
    const result = await authorize(request.url, index === 1);
    assert(result.usedPassword === (index === 0), 'SSO did not reuse the first client session');

    stage = `${app}: processing the actual callback with UserManager`;
    const manager = new UserManager(settings);
    managers.push(manager);
    const user = await manager.signinRedirectCallback(result.callback);
    const idClaims = decode(user.id_token);
    const accessClaims = decode(user.access_token);
    assert(idClaims.nonce === signin.nonce, 'ID token nonce mismatch');
    assert(typeof user.profile.sub === 'string' && user.profile.sub.length > 0, 'Missing immutable identity');
    assert(user.profile.preferred_username === 'alice.it', 'Custom username mapper missing');
    assert(user.profile.department === 'IT', 'Custom department mapper missing');
    assert(accessClaims.sub === user.profile.sub, 'Access/ID token subjects differ');
    assert(accessClaims.department === 'IT', 'Access token department missing');
    assert(accessClaims.realm_access?.roles?.includes('USER'), 'Realm role mapper missing');
    assert(expectedSubject === undefined || expectedSubject === user.profile.sub, 'SSO subjects differ');
    expectedSubject = user.profile.sub;
    assert((await manager.getUser())?.access_token === user.access_token, 'User is not available in memory');
    assert(transactionStorage.length === 0, 'Completed transaction state was not removed');
    const reloadedManager = new UserManager(createOidcSettings(config, transactionStorage));
    managers.push(reloadedManager);
    assert(await reloadedManager.getUser() === null, 'Tokens survived a page reload');

    stage = `${app}: checking the authenticated API`;
    const identityResponse = await fetch('http://localhost:8081/api/me', { headers: { Authorization: `Bearer ${user.access_token}` } });
    assert(identityResponse.status === 200, 'API rejected the library-issued access token');
    const identity = await identityResponse.json();
    assert(identity.sub === user.profile.sub && identity.department === 'IT', 'API identity differs');
    console.log(`PASS ${app}: library PKCE + nonce + callback + claims + memory-only user + API 200${index === 1 ? ' + SSO without credentials' : ''}`);
  }
} catch {
  // No URLs, authorization codes, tokens or credentials enter terminal output.
  console.error(`FAIL OIDC library integration at ${stage}.`);
  process.exitCode = 1;
} finally {
  for (const manager of managers) await manager.removeUser();
  responses.return?.();
  helper.stdin.end();
  helper.kill();
}
