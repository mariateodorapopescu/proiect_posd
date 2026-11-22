import test from 'node:test';
import assert from 'node:assert/strict';
import { THEMES, normalizeTheme, nextTheme, themeAttribute } from '../shared/theme-policy.mjs';

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
