import { StrictMode, useEffect, useState, useSyncExternalStore } from 'react';
import { createRoot } from 'react-dom/client';
import { auth, initializeAuth } from './auth';
import { appKind, config } from './config';
import { loadIdentity, type Identity } from './api';
import { Documents } from './Documents';
import { Portal } from './Portal';
import { ThemeToggle, restoreTheme } from './ThemeToggle';
import { KeyMark } from './KeyMark';
import { Backdrop, HeroScene } from './Scene';
import { messageOf } from './ui';
import './style.css';

function SignedIn({ sessionKey }: { sessionKey: string }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true; setLoading(true); setError(null);
    void loadIdentity().then(value => { if (active && auth.token() === sessionKey) setIdentity(value); }).catch(problem => { if (active) setError(messageOf(problem)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [sessionKey, attempt]);
  return <>{loading && <p role="status" className="notice info">Verific cu API-ul cine ești…</p>}{error && <div className="notice error" role="alert"><p>{error}</p><button className="secondary" onClick={() => setAttempt(attempt + 1)}>Reîncearcă</button></div>}{appKind === 'documente' ? <Documents identity={identity} /> : <Portal identity={identity} />}</>;
}

function App() {
  const state = useSyncExternalStore(auth.subscribe, auth.getSnapshot);
  const busy = state.pending !== null;
  useEffect(() => { void initializeAuth(); }, []);
  const goToTop = (event: React.MouseEvent<HTMLAnchorElement>) => { event.preventDefault(); window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }); };
  return <>
    <Backdrop />
    <a className="skip-link" href="#main">Sari la conținut</a>
    <header className="header"><a className="brand" href="/" onClick={goToTop} aria-label="SecureSync, pagina principală"><KeyMark className="brand-mark" />SecureSync</a><nav aria-label="Aplicații"><a className={appKind === 'documente' ? 'active' : ''} aria-current={appKind === 'documente' ? 'page' : undefined} href={config.documenteUrl} onClick={appKind === 'documente' ? goToTop : undefined}>Documente</a><a className={appKind === 'portal' ? 'active' : ''} aria-current={appKind === 'portal' ? 'page' : undefined} href={config.portalUrl} onClick={appKind === 'portal' ? goToTop : undefined}>Portal</a></nav><div className="account"><ThemeToggle />{state.user && <span>{state.user.profile.preferred_username || state.user.profile.name || 'Utilizator'}</span>}<button className="secondary" disabled={busy} onClick={() => void (state.user ? auth.logout() : auth.login())}>{busy ? 'Un moment…' : state.user ? 'Deconectare SSO' : 'Autentificare'}</button></div></header>
    <main id="main" tabIndex={-1}><div className="page-heading"><h1>{appKind === 'documente' ? 'Documentele echipei, la păstrare în siguranță' : 'Portalul: contul tău și ce are voie să facă'}</h1><p>{appKind === 'documente' ? 'Încarci un PDF, îl găsesc colegii din același departament și nimeni altcineva. Fiecare cerere către API trece prin OAuth 2.0.' : 'Vezi cu ce drepturi te recunoaște API-ul și încearcă singur cum răspunde când ai token și când nu ai.'}</p></div>
      {state.error && <p className="notice error" role="alert">{state.error}</p>}
      {!state.user ? <section className="section welcome">
        <div>
          <h2>Intră în cont ca să continui</h2>
          <p className="muted">Parola nu trece pe la noi: autentificarea o face Keycloak. Ce vezi apoi depinde de rolul, scope-urile și departamentul contului tău.</p>
          <ol className="flow"><li>Te autentifici la Keycloak</li><li>Primești un token, ținut doar în memoria paginii</li><li>API-ul îl verifică la fiecare cerere</li></ol>
          <div className="button-row">
            <button type="button" disabled={busy} onClick={() => void auth.login()}>{state.pending === 'login' ? 'Te trimit la Keycloak…' : 'Continuă cu Keycloak'}</button>
            <button type="button" className="secondary" disabled={busy} onClick={() => void auth.register()}>{state.pending === 'register' ? 'Deschid înregistrarea…' : 'Înregistrare'}</button>
          </div>
          <p className="small muted">Tokenul stă doar în memoria paginii. Dacă o reîncarci, intri din nou prin SSO.</p>
        </div>
        <HeroScene />
      </section> : <SignedIn key={state.user.access_token} sessionKey={state.user.access_token} />}
    </main><footer><span>SecureSync · proiect pentru cursul Politici în Sisteme Distribuite, 2026</span><span>OAuth 2.0 și OIDC · Authorization Code cu PKCE</span></footer>
  </>;
}

restoreTheme();
createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
