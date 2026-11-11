import test from 'node:test';
import assert from 'node:assert/strict';
import { callbackKind, errorMessage, isCurrentSession, validatePdf, validateTitle } from '../shared/policy.mjs';
import { InMemoryWebStorage } from 'oidc-client-ts';
import { createOidcSettings, createSigninArgs } from '../shared/oidc-settings.mjs';

test('each login binds the ID token to a fresh nonce', () => {
  const first = createSigninArgs();
  const second = createSigninArgs();
  assert.match(first.nonce, /^[0-9a-f-]{36}$/);
  assert.notEqual(first.nonce, second.nonce);
});

test('reload keeps only the OIDC transaction, never tokens or the user', async () => {
  const transactionStorage = new InMemoryWebStorage();
  const config = { authority: 'http://localhost:8080/realms/securesync', clientId: 'securesync-documente', redirectUri: 'http://localhost:3001/' };
  const firstPage = createOidcSettings(config, transactionStorage);
  await firstPage.userStore.set('user', JSON.stringify({ access_token:'secret-access', id_token:'secret-id', refresh_token:'secret-refresh' }));
  await firstPage.stateStore.set('request', JSON.stringify({ state:'random', code_verifier:'verifier' }));
  const reloadedPage = createOidcSettings(config, transactionStorage);
  assert.equal((await reloadedPage.userStore.get('user')) == null, true);
  assert.match(await reloadedPage.stateStore.get('request'), /verifier/);
  assert.equal(transactionStorage.length, 1);
  assert.doesNotMatch(transactionStorage.getItem(transactionStorage.key(0)), /secret/);
  assert.equal(firstPage.response_type, 'code');
  assert.equal(firstPage.scope, 'openid documents:read documents:write');
  assert.equal(firstPage.disablePKCE, false);
  assert.equal(firstPage.automaticSilentRenew, false);
});

test('a stale failure cannot invalidate a newer session', () => {
  assert.equal(isCurrentSession('old-token', 'new-token'), false);
  assert.equal(isCurrentSession('old-token', null), false);
  assert.equal(isCurrentSession(null, null), false);
  assert.equal(isCurrentSession('current', 'current'), true);
});
test('handles successful/error authorization callbacks and logout separately', () => {
  assert.equal(callbackKind('?code=code&state=random'), 'signin');
  assert.equal(callbackKind('?error=access_denied&state=random'), 'signin');
  assert.equal(callbackKind('?state=random'), 'signout');
  assert.equal(callbackKind('?code=unbound'), null);
  assert.equal(callbackKind(''), null);
});
test('PDF validation rejects missing, empty, non-PDF and oversized files', () => {
  assert.match(validatePdf(null), /Selectează/);
  assert.match(validatePdf({ name:'file.pdf', size:0, type:'application/pdf' }), /Selectează/);
  assert.match(validatePdf({ name:'file.pdf', size:10*1024*1024+1, type:'application/pdf' }), /10 MiB/);
  assert.match(validatePdf({ name:'file.exe', size:200, type:'application/pdf' }), /extensia/);
  assert.match(validatePdf({ name:'file.pdf', size:200, type:'text/plain' }), /extensia/);
  assert.equal(validatePdf({ name:'FILE.PDF', size:10*1024*1024, type:'application/pdf' }), null);
});
test('document title validation matches the API boundary of 160 characters', () => {
  assert.equal(validateTitle('a'.repeat(160)), null);
  assert.equal(validateTitle(`  ${'a'.repeat(160)}  `), null);
  assert.match(validateTitle('a'.repeat(161)), /160/);
  assert.match(validateTitle('  \t '), /obligatoriu/);
  assert.match(validateTitle(null), /obligatoriu/);
});

test('authentication and server errors use safe useful messages', () => {
  assert.match(errorMessage(401, 'server internals'), /Autentifică/);
  assert.match(errorMessage(403), /Acces refuzat/);
  assert.doesNotMatch(errorMessage(500, 'database password'), /password/);
  assert.equal(errorMessage(400, 'Titlu obligatoriu'), 'Titlu obligatoriu');
  assert.equal(errorMessage(400, 'a'.repeat(1000)).length, 240);
});
