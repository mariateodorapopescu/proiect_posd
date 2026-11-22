// Tema vizuală: "system" urmează setarea sistemului, celelalte două o forțează.
// Preferința NU este persistată (regula din .agents/security.md: fără localStorage);
// la reîncărcarea paginii se revine la "system".
export const THEMES = ['system', 'light', 'dark'];

export const THEME_LABELS = { system: 'Sistem', light: 'Luminoasă', dark: 'Întunecată' };

/** @param {unknown} value @returns {'system'|'light'|'dark'} */
export function normalizeTheme(value) {
  return value === 'light' || value === 'dark' ? value : 'system';
}

/** Următoarea temă din ciclul system → light → dark → system. */
export function nextTheme(current) {
  const index = THEMES.indexOf(normalizeTheme(current));
  return THEMES[(index + 1) % THEMES.length];
}

/** Valoarea atributului data-theme: absent pentru "system". */
export function themeAttribute(theme) {
  const normalized = normalizeTheme(theme);
  return normalized === 'system' ? null : normalized;
}
