import { UserManager, type User } from 'oidc-client-ts';
import { config } from './config';
import { callbackKind, isCurrentSession } from './policy.mjs';
import { createOidcSettings, createSigninArgs } from './oidc-settings.mjs';

// Only the short-lived redirect transaction (state/nonce/PKCE verifier) survives
// a navigation. Neither access/refresh/ID tokens nor the User enter web storage.
export const manager = new UserManager(createOidcSettings(config, window.sessionStorage));

type AuthState = { user: User | null; busy: boolean; error: string | null };
let current: AuthState = { user: null, busy: true, error: null };
const listeners = new Set<() => void>();
function publish(value: AuthState) { current = value; listeners.forEach(listener => listener()); }
export const auth = {
  getSnapshot: () => current,
  subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
  token: () => current.user?.access_token ?? null,
  async login() {
    publish({ ...current, busy: true, error: null });
    try { await manager.clearStaleState(); await manager.signinRedirect(createSigninArgs()); }
    catch { publish({ ...current, busy: false, error: 'Autentificarea nu a pornit. Verifică disponibilitatea Keycloak.' }); }
  },
  async logout() {
    const hint = current.user?.id_token;
    publish({ user: null, busy: true, error: null });
    try { await manager.signoutRedirect({ id_token_hint: hint, state: 'logout' }); }
    catch {
      await manager.removeUser();
      publish({ user: null, busy: false, error: 'Sesiunea locală a fost închisă, dar Keycloak nu a confirmat deconectarea.' });
    }
  },
  async rejectToken(sentToken: string) {
    if (!isCurrentSession(sentToken, auth.token())) return;
    await manager.removeUser();
    if (isCurrentSession(sentToken, auth.token())) publish({ user: null, busy: false, error: 'API-ul a refuzat tokenul. Autentifică-te din nou.' });
  }
};

manager.events.addAccessTokenExpired(() => {
  void manager.removeUser();
  publish({ user: null, busy: false, error: 'Tokenul a expirat. Autentifică-te din nou pentru a continua.' });
});

let initialization: Promise<void> | null = null;
export function initializeAuth() {
  initialization ??= (async () => {
    try {
      const kind = callbackKind(window.location.search);
      if (kind === 'signin') {
        try {
          const user = await manager.signinRedirectCallback();
          publish({ user: user.expired ? null : user, busy: false, error: user.expired ? 'Tokenul a expirat.' : null });
        } finally { history.replaceState({}, '', '/'); }
      } else if (kind === 'signout') {
        try { await manager.signoutRedirectCallback(); }
        finally { history.replaceState({}, '', '/'); }
        publish({ user: null, busy: false, error: null });
      } else {
        publish({ user: null, busy: false, error: null });
      }
      await manager.clearStaleState();
    } catch {
      await manager.removeUser();
      publish({ user: null, busy: false, error: 'Autentificarea nu s-a încheiat. Reîncearcă autentificarea.' });
    }
  })();
  return initialization;
}
