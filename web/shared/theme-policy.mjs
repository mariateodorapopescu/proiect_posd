// Tema vizuală: "system" urmează setarea sistemului, celelalte două o forțează.
// Preferința se păstrează într-un cookie simplu (nu în localStorage, nu în tokenuri):
// cookie-urile nu țin cont de port, deci Documente (3001) și Portal (3002) o împart.
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

export const THEME_COOKIE = 'securesync-theme';
const ONE_YEAR = 60 * 60 * 24 * 365;

/** Valoarea pentru document.cookie. "system" șterge cookie-ul (revenire la setarea sistemului). */
export function themeCookie(theme, secure = false) {
  const normalized = normalizeTheme(theme);
  const maxAge = normalized === 'system' ? 0 : ONE_YEAR;
  return `${THEME_COOKIE}=${normalized}; Path=/; Max-Age=${maxAge}; SameSite=Lax${secure ? '; Secure' : ''}`;
}

/** Citește tema din șirul document.cookie; orice valoare necunoscută devine "system". */
export function themeFromCookies(cookies) {
  const entry = String(cookies ?? '').split(';').map(part => part.trim()).find(part => part.startsWith(`${THEME_COOKIE}=`));
  return normalizeTheme(entry?.slice(THEME_COOKIE.length + 1));
}
