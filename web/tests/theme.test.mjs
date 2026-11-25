import test from 'node:test';
import assert from 'node:assert/strict';
import { THEMES, normalizeTheme, nextTheme, themeAttribute, themeCookie, themeFromCookies } from '../shared/theme-policy.mjs';

test('theme cycles system, light, dark and back', () => {
  assert.deepEqual(THEMES, ['system', 'light', 'dark']);
  assert.equal(nextTheme('system'), 'light');
  assert.equal(nextTheme('light'), 'dark');
  assert.equal(nextTheme('dark'), 'system');
});

test('unknown values fall back to the system theme', () => {
  assert.equal(normalizeTheme('blue'), 'system');
  assert.equal(normalizeTheme(undefined), 'system');
  assert.equal(nextTheme('blue'), 'light');
});

test('only forced themes set the data-theme attribute', () => {
  assert.equal(themeAttribute('system'), null);
  assert.equal(themeAttribute('light'), 'light');
  assert.equal(themeAttribute('dark'), 'dark');
});

test('theme is stored in a cookie shared by both apps and read back', () => {
  assert.match(themeCookie('dark'), /^securesync-theme=dark; Path=\/; Max-Age=31536000; SameSite=Lax$/);
  assert.match(themeCookie('dark', true), /; Secure$/);
  assert.match(themeCookie('system'), /Max-Age=0/);
  assert.equal(themeFromCookies('a=1; securesync-theme=dark; b=2'), 'dark');
  assert.equal(themeFromCookies('securesync-theme=light'), 'light');
  assert.equal(themeFromCookies('securesync-theme=altceva'), 'system');
  assert.equal(themeFromCookies(''), 'system');
  assert.equal(themeFromCookies(undefined), 'system');
});
