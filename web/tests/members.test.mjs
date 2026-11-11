import test from 'node:test';
import assert from 'node:assert/strict';
import { addsPrivilegedRole, mayManageMembers, membersErrorMessage, sameMemberAccess, validateMemberAccess } from '../shared/members-policy.mjs';
import { createOidcSettings } from '../shared/oidc-settings.mjs';
import { InMemoryWebStorage } from 'oidc-client-ts';

test('member administration requires both IMPLEMENTATOR and the management scope', () => {
  assert.equal(mayManageMembers(null), false);
  assert.equal(mayManageMembers({ roles: ['ADMIN'], scopes: ['members:manage'] }), false);
  assert.equal(mayManageMembers({ roles: ['USER'], scopes: ['members:manage'] }), false);
  assert.equal(mayManageMembers({ roles: ['IMPLEMENTATOR'], scopes: ['documents:read'] }), false);
  assert.equal(mayManageMembers({ roles: ['IMPLEMENTATOR', 'USER'], scopes: ['members:manage'] }), true);
});

test('only Portal requests the member management scope', () => {
  for (const [clientId, expected] of [['securesync-documente', false], ['securesync-portal', true]]) {
    const settings = createOidcSettings({ clientId, authority: 'http://localhost:8080', redirectUri: 'http://localhost:3002/' }, new InMemoryWebStorage());
    assert.equal(settings.scope.split(' ').includes('members:manage'), expected);
    assert.equal(settings.scope.split(' ').includes('documents:write'), true);
  }
});

test('access drafts reject empty, duplicate and arbitrary privileged roles or departments', () => {
  assert.equal(validateMemberAccess({ roles: ['USER', 'IMPLEMENTATOR'], department: 'IT' }), null);
  for (const roles of [[], ['USER', 'USER'], ['realm-admin'], ['USER', 'manage-users'], null]) {
    assert.match(validateMemberAccess({ roles, department: 'IT' }), /rol/);
  }
  assert.match(validateMemberAccess({ roles: ['USER'], department: '' }), /departamentul/);
  assert.match(validateMemberAccess({ roles: ['ADMIN'], department: 'SECURITY' }), /departamentul/);
});

test('draft comparisons ignore role ordering but preserve actual role and department changes', () => {
  const current = { roles: ['USER', 'ADMIN'], department: 'IT' };
  assert.equal(sameMemberAccess(current, { roles: ['ADMIN', 'USER'], department: 'IT' }), true);
  assert.equal(sameMemberAccess(current, { roles: ['USER'], department: 'IT' }), false);
  assert.equal(sameMemberAccess(current, { roles: ['USER', 'ADMIN'], department: 'HR' }), false);
});

test('a new privileged role requires review while ordinary changes do not', () => {
  const current = { roles: ['USER'], department: 'IT' };
  assert.equal(addsPrivilegedRole(current, { roles: ['USER', 'ADMIN'], department: 'IT' }), true);
  assert.equal(addsPrivilegedRole(current, { roles: ['IMPLEMENTATOR'], department: 'IT' }), true);
  assert.equal(addsPrivilegedRole(current, { roles: ['USER'], department: 'HR' }), false);
  assert.equal(addsPrivilegedRole({ roles: ['USER', 'ADMIN'] }, { roles: ['ADMIN'] }), false);
});

test('management errors explain revoked access and partial provider failures', () => {
  assert.match(membersErrorMessage(403), /IMPLEMENTATOR/);
  assert.doesNotMatch(membersErrorMessage(403), /document policy/);
  assert.match(membersErrorMessage(503), /Actualizează lista/);
  assert.match(membersErrorMessage(409), /protejat/);
  assert.equal(membersErrorMessage(401), null);
});
