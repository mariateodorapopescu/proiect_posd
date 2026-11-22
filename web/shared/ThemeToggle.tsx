import { useState } from 'react';
import { THEME_LABELS, nextTheme, themeAttribute } from './theme-policy.mjs';

type Theme = keyof typeof THEME_LABELS;

function applyTheme(theme: Theme) {
  const attribute = themeAttribute(theme);
  if (attribute) document.documentElement.dataset.theme = attribute;
  else delete document.documentElement.dataset.theme;
}

/** Comutator de temă (sistem / luminoasă / întunecată), doar în memorie. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('system');
  const change = () => { const next = nextTheme(theme) as Theme; applyTheme(next); setTheme(next); };
  return <button type="button" className="secondary theme-toggle" onClick={change} aria-label={`Temă: ${THEME_LABELS[theme]}. Apasă pentru a schimba.`}>
    <span aria-hidden="true">{theme === 'dark' ? '☾' : theme === 'light' ? '☀' : '◐'}</span>
    <span className="theme-label">{THEME_LABELS[theme]}</span>
  </button>;
}
