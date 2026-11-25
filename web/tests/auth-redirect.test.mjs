import assert from 'node:assert/strict';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { InMemoryWebStorage } from 'oidc-client-ts';
import { createServer } from 'vite';

test('returning from Keycloak releases the login and registration actions', { timeout: 10000 }, async t => {
  const app = new URL('http://localhost:3001/');
  const issuer = 'http://localhost:8080/realms/securesync';
  const authorization = `${issuer}/protocol/openid-connect/auth`;
  const storage = new InMemoryWebStorage();
  let finishNavigation;

  const browser = Object.assign(new EventTarget(), {
    location: { href: app.href, origin: app.origin, search: '', assign: url => finishNavigation(new URL(url)) },
    sessionStorage: storage,
  });
  browser.self = browser;
  globalThis.window = browser;
  globalThis.document = { body: { dataset: { app: 'documente' } } };
  t.after(() => { delete globalThis.window; delete globalThis.document; });
  t.mock.method(globalThis, 'fetch', async url => {
    assert.equal(url, `${issuer}/.well-known/openid-configuration`);
    return Response.json({ issuer, authorization_endpoint: authorization });
  });

  const vite = await createServer({
    root: fileURLToPath(new URL('../', import.meta.url)),
    configFile: false,
    envFile: false,
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, hmr: false, watch: null },
  });
  t.after(() => vite.close());
  const { auth, initializeAuth } = await vite.ssrLoadModule('/shared/auth.ts');
  await initializeAuth();
  const ready = auth.getSnapshot();

  for (const [action, prompt] of [['login', null], ['register', 'create']]) {
    const navigation = new Promise(resolve => { finishNavigation = resolve; });
    const redirect = auth[action]();
    const url = await navigation;
    assert.equal(url.origin + url.pathname, authorization);
    assert.equal(url.searchParams.get('prompt'), prompt);
    assert.equal(url.searchParams.get('code_challenge_method'), 'S256');
    assert.ok(url.searchParams.get('nonce'));
    assert.notDeepEqual(auth.getSnapshot(), ready, 'The redirect is still in flight');

    // The installed OIDC navigator receives this event when Back restores the page.
    browser.dispatchEvent(Object.assign(new Event('pageshow'), { persisted: true }));
    await redirect;
    assert.deepEqual(auth.getSnapshot(), ready, 'Both actions are available again after Back');
    assert.ok(storage.getItem(`securesync-documente.oidc.${url.searchParams.get('state')}`),
      'The PKCE transaction is available if the user goes Forward to finish');
  }
});
