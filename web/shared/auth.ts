import { UserManager, type User } from 'oidc-client-ts';
import { config } from './config';
import { callbackKind, isCurrentSession } from './policy.mjs';
import { createOidcSettings, createSigninArgs } from './oidc-settings.mjs';

// Only the short-lived redirect transaction (state/nonce/PKCE verifier) survives
// a navigation. Neither access/refresh/ID tokens nor the User enter web storage.
export const manager = new UserManager(createOidcSettings(config, window.sessionStorage));

type RedirectAction = 'login' | 'register' | 'logout';
type AuthState = { user: User | null; pending: 'initializing' | RedirectAction | null; error: string | null };
let current: AuthState = { user: null, pending: 'initializing', error: null };
const listeners = new Set<() => void>();
function publish(value: AuthState) { current = value; listeners.forEach(listener => listener()); }

async function redirect(action: RedirectAction, navigate: () => Promise<void>, failureMessage: string) {
  if (current.pending) return;
  const started: AuthState = { user: action === 'logout' ? null : current.user, pending: action, error: null };
  publish(started);
  let error: string | null = null;
  try {
    await navigate();
  } catch {
    error = failureMessage;
  } finally {
    // The OIDC navigator resolves on pageshow when Back restores this page.
    if (current === started) publish({ ...started, pending: null, error });
  }
}

function signIn(action: 'login' | 'register') {
  const registration = action === 'register';
  return redirect(action, () => manager.signinRedirect({
    ...createSigninArgs(),
    prompt: registration ? 'create' : undefined,
  }), registration ? 'Înregistrarea nu s-a deschis. Verifică disponibilitatea Keycloak.'
    : 'Autentificarea nu a pornit. Verifică disponibilitatea Keycloak.');
}

export const auth = {
  getSnapshot: () => current,
  subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
  token: () => current.user?.access_token ?? null,
  login: () => signIn('login'),
  register: () => signIn('register'),
  logout() {
    const hint = current.user?.id_token;
    return redirect('logout', async () => {
      try { await manager.signoutRedirect({ id_token_hint: hint, state: 'logout' }); }
      catch (error) { await manager.removeUser(); throw error; }
    }, 'Sesiunea locală a fost închisă, dar Keycloak nu a confirmat deconectarea.');
  },
  async rejectToken(sentToken: string) {
    if (!isCurrentSession(sentToken, auth.token())) return;
    await manager.removeUser();
    if (isCurrentSession(sentToken, auth.token())) publish({ user: null, pending: null, error: 'API-ul a refuzat tokenul. Autentifică-te din nou.' });
  }
};

manager.events.addAccessTokenExpired(() => {
  void manager.removeUser();
  publish({ user: null, pending: null, error: 'Tokenul a expirat. Autentifică-te din nou pentru a continua.' });
});

let initialization: Promise<void> | null = null;
export function initializeAuth() {
  initialization ??= (async () => {
    try {
      const kind = callbackKind(window.location.search);
      if (kind === 'signin') {
        try {
          const user = await manager.signinRedirectCallback();
          publish({ user: user.expired ? null : user, pending: null, error: user.expired ? 'Tokenul a expirat.' : null });
        } finally { history.replaceState({}, '', '/'); }
      } else if (kind === 'signout') {
        try { await manager.signoutRedirectCallback(); }
        finally { history.replaceState({}, '', '/'); }
        publish({ user: null, pending: null, error: null });
      } else {
        publish({ user: null, pending: null, error: null });
      }
      await manager.clearStaleState();
    } catch {
      await manager.removeUser();
      publish({ user: null, pending: null, error: 'Autentificarea nu s-a încheiat. Reîncearcă autentificarea.' });
    }
  })();
  return initialization;
}
