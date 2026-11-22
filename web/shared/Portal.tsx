import { useState } from 'react';
import { config } from './config';
import { ApiError, request, type Identity } from './api';
import { Members } from './Members';
import { RevocationMonitor } from './RevocationMonitor';
import { mayManageMembers } from './members-policy.mjs';
import { messageOf } from './ui';

export function Portal({ identity }: { identity: Identity | null }) {
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
    <RevocationMonitor identity={identity} />
    <section className="section sso-section"><div><p className="eyebrow">Două aplicații, o singură autentificare</p><h2>Continuă în Documente</h2><p className="muted">Deschide aplicația și apasă „Autentificare”. Keycloak poate folosi sesiunea SSO deja deschisă, fără reintroducerea parolei.</p></div><a className="button" href={config.documenteUrl}>Deschide Documente <span aria-hidden="true">↗</span></a></section>
    </div>
  </>;
}
