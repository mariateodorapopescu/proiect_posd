import { StrictMode, useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { auth, initializeAuth } from './auth';
import { appKind, config } from './config';
import { ApiError, deleteDocument, downloadDocument, listDocuments, loadIdentity, request, uploadDocument, type DocumentInfo, type Identity } from './api';
import { TITLE_MAX_LENGTH, validatePdf, validateTitle } from './policy.mjs';
import { Members } from './Members';
import { mayManageMembers } from './members-policy.mjs';
import './style.css';

const messageOf = (error: unknown) => error instanceof Error ? error.message : 'Cererea nu a putut fi finalizată.';
const dateFormat = new Intl.DateTimeFormat('ro-RO', { dateStyle: 'medium', timeStyle: 'short' });

function Documents({ identity }: { identity: Identity | null }) {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const session = auth.token();
  const active = useRef(true);
  const loadSequence = useRef(0);
  useEffect(() => () => { active.current = false; }, []);

  async function reload() {
    const sequence = ++loadSequence.current;
    setLoading(true); setError(null);
    try { const items = await listDocuments(); if (active.current && sequence === loadSequence.current && auth.token() === session) { setDocuments(items); setHasLoaded(true); } }
    catch (problem) { if (active.current && sequence === loadSequence.current) setError(messageOf(problem)); }
    finally { if (active.current && sequence === loadSequence.current) setLoading(false); }
  }
  useEffect(() => { active.current = true; void reload(); return () => { active.current = false; }; }, []);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    const fileError = validatePdf(file);
    const title = new FormData(event.currentTarget).get('title')?.toString().trim() || '';
    const titleError = validateTitle(title);
    if (titleError) { setError(titleError); return; }
    if (fileError || !file) { setError(fileError); return; }
    setBusy(true); setError(null); setNotice(null);
    try {
      await uploadDocument(title, file);
      if (!active.current || auth.token() !== session) return;
      form.current?.reset(); setNotice('Documentul a fost încărcat.'); await reload();
    } catch (problem) { if (active.current) setError(messageOf(problem)); }
    finally { if (active.current) setBusy(false); }
  }

  async function act(document: DocumentInfo, operation: 'download' | 'delete') {
    setBusy(true); setError(null); setNotice(null);
    try {
      if (operation === 'download') await downloadDocument(document);
      else {
        await deleteDocument(document.id);
        if (!active.current || auth.token() !== session) return;
        setNotice('Documentul a fost șters.'); setPendingDelete(null); await reload();
      }
    } catch (problem) { if (active.current) setError(messageOf(problem)); }
    finally { if (active.current) setBusy(false); }
  }

  const mayWrite = identity?.scopes.includes('documents:write') && identity.roles.some(role => role === 'USER' || role === 'ADMIN');
  return <>
    <section className="section" aria-labelledby="upload-title">
      <div className="section-heading"><div><p className="eyebrow">Bibliotecă privată</p><h2 id="upload-title">Încarcă un document</h2></div><span className="tag">PDF · maximum 10 MiB</span></div>
      <p className="muted">Documentele sunt disponibile proprietarului, colegilor din același departament și administratorilor.</p>
      <form ref={form} onSubmit={upload} className="upload-form">
        <label>Titlu<input name="title" type="text" required maxLength={TITLE_MAX_LENGTH} placeholder="Ex. Ghid de lucru" disabled={busy || !mayWrite} /></label>
        <label>Fișier PDF<input ref={fileInput} name="file" type="file" accept="application/pdf,.pdf" required disabled={busy || !mayWrite} /></label>
        <button type="submit" disabled={busy || !mayWrite}>{busy ? 'Se procesează…' : 'Încarcă PDF'}</button>
      </form>
      {identity && !mayWrite && <p className="muted">Contul curent nu are drept de încărcare.</p>}
    </section>
    <div aria-live="polite">{notice && <p className="notice success">{notice}</p>}</div>
    {error && <p className="notice error" role="alert">{error}</p>}
    <section className="section" aria-labelledby="documents-title" aria-busy={loading}>
      <div className="section-heading"><div><p className="eyebrow">Acces autorizat prin API</p><h2 id="documents-title">Documentele disponibile</h2></div><button className="secondary" onClick={() => void reload()} disabled={loading || busy}>Actualizează</button></div>
      {loading ? <p className="muted" role="status">Se încarcă documentele…</p> : !hasLoaded ? <p className="muted">Lista nu a putut fi încărcată. Folosește „Actualizează” pentru a reîncerca.</p> : documents.length === 0 ? <div className="empty"><span className="file-icon" aria-hidden="true">PDF</span><h3>Niciun document disponibil</h3><p className="muted">Încarcă primul PDF sau verifică departamentul și drepturile contului.</p></div> : <ul className="document-list">{documents.map(document => {
        const canDelete = mayWrite && (identity?.sub === document.ownerId || identity?.roles.includes('ADMIN'));
        return <li key={document.id} className="document">
          <span className="file-icon" aria-hidden="true">PDF</span><div className="document-info"><h3>{document.title}</h3><p>{document.originalFilename} <span aria-hidden="true">·</span> {(document.size / 1024).toFixed(1)} KiB</p><p className="muted">{document.department} · {dateFormat.format(new Date(document.createdAt))}{identity?.sub === document.ownerId ? ' · Încărcat de tine' : ''}</p></div>
          <div className="document-actions"><button className="secondary" disabled={busy} onClick={() => void act(document, 'download')}>Descarcă</button>{canDelete && <button className="text danger" disabled={busy} onClick={() => setPendingDelete(document.id)}>Șterge</button>}</div>
          {pendingDelete === document.id && <div className="delete-confirm" role="group" aria-label={`Confirmă ștergerea ${document.title}`}><p>Ștergi definitiv acest document?</p><button className="danger-button" disabled={busy} onClick={() => void act(document, 'delete')}>Da, șterge</button><button className="secondary" disabled={busy} onClick={() => setPendingDelete(null)}>Anulează</button></div>}
        </li>;
      })}</ul>}
    </section>
  </>;
}

function Portal({ identity }: { identity: Identity | null }) {
  const [tab, setTab] = useState<'account' | 'members'>('account');
  const [membersVisited, setMembersVisited] = useState(false);
  const [probe, setProbe] = useState<{ status: number; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  async function check(authenticated: boolean) {
    setBusy(true); setProbe(null);
    try { const response = await request('/api/documents', {}, authenticated); setProbe({ status: response.status, text: 'Acces permis de API.' }); }
    catch (error) { setProbe({ status: error instanceof ApiError ? error.status : 0, text: messageOf(error) }); }
    finally { setBusy(false); }
  }
  const management = mayManageMembers(identity);
  const selectedTab = management && tab === 'members' ? 'members' : 'account';
  return <>
    <div className="portal-tabs" role="tablist" aria-label="Secțiunile Portalului"><button type="button" id="account-tab" role="tab" aria-selected={selectedTab === 'account'} aria-controls="account-panel" className={selectedTab === 'account' ? 'selected' : 'secondary'} onClick={() => setTab('account')}>Contul meu</button>{management && <button type="button" id="members-tab" role="tab" aria-selected={selectedTab === 'members'} aria-controls="members-panel" className={selectedTab === 'members' ? 'selected' : 'secondary'} onClick={() => { setMembersVisited(true); setTab('members'); }}>Administrare membri</button>}</div>
    {management && identity && membersVisited && <div id="members-panel" role="tabpanel" aria-labelledby="members-tab" hidden={selectedTab !== 'members'}><Members identity={identity} /></div>}
    <div id="account-panel" role="tabpanel" aria-labelledby="account-tab" hidden={selectedTab !== 'account'}>
    <section className="section" aria-labelledby="identity-title"><p className="eyebrow">Identitate verificată de API</p><h2 id="identity-title">Contul și drepturile tale</h2>
      {identity ? <dl className="identity-grid"><div><dt>Utilizator</dt><dd>{identity.username}</dd></div><div><dt>Departament</dt><dd>{identity.department || 'Nespecificat'}</dd></div><div><dt>Roluri</dt><dd>{identity.roles.join(', ') || 'Niciun rol'}</dd></div><div><dt>Strategie de validare</dt><dd>{identity.strategy}</dd></div><div className="wide"><dt>Scope-uri</dt><dd className="tags">{identity.scopes.map(scope => <span className="tag" key={scope}>{scope}</span>)}</dd></div><div className="wide"><dt>Identificator OIDC</dt><dd className="identifier">{identity.sub}</dd></div></dl> : <p className="muted">Identitatea nu a fost încă verificată de API.</p>}
    </section>
    <section className="section" aria-labelledby="probe-title"><p className="eyebrow">Controlul accesului</p><h2 id="probe-title">Verifică răspunsul API-ului</h2><p className="muted">Ambele cereri folosesc endpoint-ul de documente. API-ul decide accesul pe baza scope-ului, rolului și atributelor.</p><div className="button-row"><button onClick={() => void check(true)} disabled={busy}>Cerere cu token</button><button className="secondary" onClick={() => void check(false)} disabled={busy}>Cerere fără token</button></div><div aria-live="polite">{busy && <p>Se verifică…</p>}{probe && <p className={`notice ${probe.status === 200 ? 'success' : 'info'}`}><strong>{probe.status ? `HTTP ${probe.status}` : 'Fără răspuns'}</strong> · {probe.text}</p>}</div></section>
    <section className="section sso-section"><div><p className="eyebrow">Două aplicații, o singură autentificare</p><h2>Continuă în Documente</h2><p className="muted">Deschide aplicația și apasă „Autentificare”. Keycloak poate folosi sesiunea SSO deja deschisă, fără reintroducerea parolei.</p></div><a className="button" href={config.documenteUrl}>Deschide Documente <span aria-hidden="true">↗</span></a></section>
    </div>
  </>;
}

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
  const goToTop = (event: React.MouseEvent<HTMLAnchorElement>) => { event.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  return <>
    <header className="header"><a className="brand" href="/" onClick={goToTop} aria-label="SecureSync, pagina principală"><span className="brand-mark" aria-hidden="true">S</span>SecureSync</a><nav aria-label="Aplicații"><a className={appKind === 'documente' ? 'active' : ''} aria-current={appKind === 'documente' ? 'page' : undefined} href={config.documenteUrl} onClick={appKind === 'documente' ? goToTop : undefined}>Documente</a><a className={appKind === 'portal' ? 'active' : ''} aria-current={appKind === 'portal' ? 'page' : undefined} href={config.portalUrl} onClick={appKind === 'portal' ? goToTop : undefined}>Portal</a></nav><div className="account">{state.user && <span>{state.user.profile.preferred_username || state.user.profile.name || 'Utilizator'}</span>}<button className="secondary" disabled={state.busy} onClick={() => void (state.user ? auth.logout() : auth.login())}>{state.busy ? 'Se conectează…' : state.user ? 'Deconectare SSO' : 'Autentificare'}</button></div></header>
    <main><div className="page-heading"><p className="eyebrow">Politici în Sisteme Distribuite · Tema 10</p><h1>{appKind === 'documente' ? 'Documente, cu acces controlat.' : 'Un singur cont. Acces verificat.'}</h1><p>{appKind === 'documente' ? 'Încarcă și descarcă PDF-uri printr-un API protejat cu OAuth 2.0.' : 'Consultă drepturile contului și verifică politica de acces la resurse.'}</p></div>
      {state.error && <p className="notice error" role="alert">{state.error}</p>}
      {!state.user ? <section className="section welcome"><span className="welcome-symbol" aria-hidden="true">S</span><div><p className="eyebrow">SecureSync / {appKind === 'documente' ? 'Documente' : 'Portal'}</p><h2>Autentifică-te pentru a continua</h2><p className="muted">Autentificarea este gestionată de Keycloak. Accesul la documente depinde de rolul, scope-urile și departamentul contului.</p><button disabled={state.busy} onClick={() => void auth.login()}>{state.busy ? 'Se pregătește autentificarea…' : 'Continuă cu Keycloak'}</button><p className="small muted">Tokenurile sunt păstrate doar în memoria aplicației. După reîncărcarea paginii, folosește din nou autentificarea SSO.</p></div></section> : <SignedIn key={state.user.access_token} sessionKey={state.user.access_token} />}
    </main><footer><span>SecureSync · Proiect educațional 2026</span><span>OAuth 2.0 / OIDC · Authorization Code + PKCE</span></footer>
  </>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
