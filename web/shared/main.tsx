import { StrictMode, useEffect, useState, useSyncExternalStore } from 'react';
import { createRoot } from 'react-dom/client';
import { auth, initializeAuth } from './auth';
import { appKind, config } from './config';
import { loadIdentity, type Identity } from './api';
import { Documents } from './Documents';
import { Portal } from './Portal';
import { ThemeToggle } from './ThemeToggle';
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
  return <>{loading && <p role="status" className="notice info">Se verifică identitatea la API…</p>}{error && <div className="notice error" role="alert"><p>{error}</p><button className="secondary" onClick={() => setAttempt(attempt + 1)}>Reîncearcă</button></div>}{appKind === 'documente' ? <Documents identity={identity} /> : <Portal identity={identity} />}</>;
}

function App() {
  const state = useSyncExternalStore(auth.subscribe, auth.getSnapshot);
  useEffect(() => { void initializeAuth(); }, []);
  const goToTop = (event: React.MouseEvent<HTMLAnchorElement>) => { event.preventDefault(); window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }); };
  return <>
    <a className="skip-link" href="#main">Sari la conținut</a>
    <header className="header"><a className="brand" href="/" onClick={goToTop} aria-label="SecureSync, pagina principală"><span className="brand-mark" aria-hidden="true">S</span>SecureSync</a><nav aria-label="Aplicații"><a className={appKind === 'documente' ? 'active' : ''} aria-current={appKind === 'documente' ? 'page' : undefined} href={config.documenteUrl} onClick={appKind === 'documente' ? goToTop : undefined}>Documente</a><a className={appKind === 'portal' ? 'active' : ''} aria-current={appKind === 'portal' ? 'page' : undefined} href={config.portalUrl} onClick={appKind === 'portal' ? goToTop : undefined}>Portal</a></nav><div className="account"><ThemeToggle />{state.user && <span>{state.user.profile.preferred_username || state.user.profile.name || 'Utilizator'}</span>}<button className="secondary" disabled={state.busy} onClick={() => void (state.user ? auth.logout() : auth.login())}>{state.busy ? 'Se conectează…' : state.user ? 'Deconectare SSO' : 'Autentificare'}</button></div></header>
    <main id="main" tabIndex={-1}><div className="page-heading"><p className="eyebrow">Politici în Sisteme Distribuite · Tema 10</p><h1>{appKind === 'documente' ? 'Documente, cu acces controlat.' : 'Un singur cont. Acces verificat.'}</h1><p>{appKind === 'documente' ? 'Încarcă și descarcă PDF-uri printr-un API protejat cu OAuth 2.0.' : 'Consultă drepturile contului și verifică politica de acces la resurse.'}</p></div>
      {state.error && <p className="notice error" role="alert">{state.error}</p>}
      {!state.user ? <section className="section welcome"><span className="welcome-symbol" aria-hidden="true">S</span><div><p className="eyebrow">SecureSync / {appKind === 'documente' ? 'Documente' : 'Portal'}</p><h2>Autentifică-te pentru a continua</h2><p className="muted">Autentificarea este gestionată de Keycloak. Accesul la documente depinde de rolul, scope-urile și departamentul contului.</p><button disabled={state.busy} onClick={() => void auth.login()}>{state.busy ? 'Se pregătește autentificarea…' : 'Continuă cu Keycloak'}</button><p className="small muted">Tokenurile sunt păstrate doar în memoria aplicației. După reîncărcarea paginii, folosește din nou autentificarea SSO.</p></div></section> : <SignedIn key={state.user.access_token} sessionKey={state.user.access_token} />}
    </main><footer><span>SecureSync · Proiect educațional 2026</span><span>OAuth 2.0 / OIDC · Authorization Code + PKCE</span></footer>
  </>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
