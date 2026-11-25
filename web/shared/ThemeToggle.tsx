import { useState } from 'react';
import { THEME_LABELS, nextTheme, themeAttribute, themeCookie, themeFromCookies } from './theme-policy.mjs';

type Theme = keyof typeof THEME_LABELS;

function applyTheme(theme: Theme) {
  const attribute = themeAttribute(theme);
  if (attribute) document.documentElement.dataset.theme = attribute;
  else delete document.documentElement.dataset.theme;
}

/** Aplică tema salvată în cookie, înainte de prima afișare (fără sclipire la schimbarea aplicației). */
export function restoreTheme(): Theme {
  const theme = themeFromCookies(document.cookie) as Theme;
  applyTheme(theme);
  return theme;
}

/** Comutator de temă (sistem / luminoasă / întunecată). Alegerea se păstrează într-un cookie comun celor două aplicații. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => themeFromCookies(document.cookie) as Theme);
  const change = () => { const next = nextTheme(theme) as Theme; applyTheme(next); document.cookie = themeCookie(next, location.protocol === 'https:'); setTheme(next); };
  return <button type="button" className="secondary theme-toggle" onClick={change} aria-label={`Temă: ${THEME_LABELS[theme]}. Apasă pentru a schimba.`}>
    <span aria-hidden="true">{theme === 'dark' ? '☾' : theme === 'light' ? '☀' : '◐'}</span>
    <span className="theme-label">{THEME_LABELS[theme]}</span>
  </button>;
}
