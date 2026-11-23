import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// Verifică perechile de culori din style.css în ambele teme (prag WCAG AA, 4.5:1 pentru text).
const css = readFileSync(new URL('../shared/style.css', import.meta.url), 'utf8');
const themed = {};
for (const [, name, light, dark] of css.matchAll(/--([\w-]+):\s*light-dark\((#[0-9a-f]{6}),\s*(#[0-9a-f]{6})\)/gi)) themed[name] = { light, dark };
const fixed = {};
for (const [, name, value] of css.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6});/gi)) if (!themed[name]) fixed[name] = value;

const channel = value => { const c = value / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const luminance = hex => { const n = parseInt(hex.slice(1), 16); return .2126 * channel(n >> 16) + .7152 * channel((n >> 8) & 255) + .0722 * channel(n & 255); };
const ratio = (a, b) => { const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p); return (x + .05) / (y + .05); };
const pick = (name, theme) => themed[name]?.[theme] ?? fixed[name] ?? (/^#[0-9a-f]{6}$/i.test(name) ? name : undefined);

const pairs = [
  ['text', 'bg'], ['text', 'surface'], ['muted', 'bg'], ['muted', 'surface'], ['muted', 'surface-muted'], ['muted', 'surface-hover'],
  ['accent', 'bg'], ['accent', 'surface'], ['accent-hover', 'surface-muted'], ['on-accent', 'accent'], ['on-accent', 'accent-hover'],
  ['icon-text', 'icon-bg'], ['danger', 'bg'], ['danger', 'danger-wash'], ['#ffffff', 'danger-solid'], ['#ffffff', 'danger-solid-hover'],
  ['error-text', 'error-bg'], ['success-text', 'success-bg'], ['info-text', 'info-bg'], ['probe-text', 'probe-allowed'], ['probe-text', 'probe-denied'], ['probe-text', 'probe-neutral'],
  ['focus', 'bg'], ['focus', 'surface'], ['tag-text', 'tag-bg'], ['tag-text', 'mark'], ['text', 'mark'], ['ink', 'surface'],
];

for (const theme of ['light', 'dark']) {
  test(`contrast ${theme}`, () => {
    for (const [foreground, background] of pairs) {
      const a = pick(foreground, theme), b = pick(background, theme);
      assert.ok(a && b, `missing token in pair ${foreground}/${background}`);
      assert.ok(ratio(a, b) >= 4.5, `${foreground} on ${background} (${theme}): ${ratio(a, b).toFixed(2)}:1`);
    }
  });
}
