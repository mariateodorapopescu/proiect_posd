import { useEffect, useRef, useState, type FormEvent } from 'react';
import { auth } from './auth';
import { ApiError, listMembers, updateMemberAccess, type Identity, type Member, type MemberAccess } from './api';
import { addsPrivilegedRole, MEMBER_DEPARTMENTS, MEMBER_ROLES, membersErrorMessage, sameMemberAccess, validateMemberAccess } from './members-policy.mjs';

const accessOf = (member: Member): MemberAccess => ({ roles: [...member.roles], department: member.department });
const messageOf = (error: unknown) => error instanceof ApiError
  ? membersErrorMessage(error.status) || error.message
  : 'Administrarea membrilor nu a putut fi finalizată.';
type Navigation = { search: string; page: number };

export function Members({ identity }: { identity: Identity }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [drafts, setDrafts] = useState<Record<string, MemberAccess>>({});
  const [searchText, setSearchText] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);
  const [review, setReview] = useState<{ id: string; access: MemberAccess } | null>(null);
  const [pendingNavigation, setPendingNavigation] = useState<Navigation | null>(null);
  const active = useRef(false);
  const sequence = useRef(0);
  const session = auth.token();
  const currentSession = () => active.current && auth.token() === session;
  const dirty = members.some(member => drafts[member.id] && !sameMemberAccess(member, drafts[member.id]));

  useEffect(() => {
    active.current = true;
    return () => { active.current = false; sequence.current++; };
  }, []);

  useEffect(() => {
    const requestSequence = ++sequence.current;
    const controller = new AbortController();
    setLoading(true); setError(null); setRowErrors({}); setReview(null);
    void listMembers(search, page, controller.signal).then(result => {
      if (!currentSession() || requestSequence !== sequence.current) return;
      setMembers(result.members);
      setDrafts(Object.fromEntries(result.members.map(member => [member.id, accessOf(member)])));
      setHasMore(result.hasMore); setLoaded(true); setDenied(false);
    }).catch(problem => {
      if (!currentSession() || requestSequence !== sequence.current) return;
      setError(messageOf(problem));
      if (problem instanceof ApiError && problem.status === 403) {
        setDenied(true); setMembers([]); setDrafts({});
      }
    }).finally(() => {
      if (currentSession() && requestSequence === sequence.current) setLoading(false);
    });
    return () => controller.abort();
  }, [search, page, attempt]);

  function navigate(next: Navigation, confirmed = false) {
    if (busyId) return;
    if (dirty && !confirmed) { setPendingNavigation(next); return; }
    setPendingNavigation(null); setReview(null); setNotice(null); setMembers([]); setDrafts({});
    setSearch(next.search); setPage(next.page); setAttempt(value => value + 1);
  }

  function searchMembers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (searchText.trim().length > 80) { setError('Căutarea poate avea cel mult 80 de caractere.'); return; }
    navigate({ search: searchText.trim(), page: 0 });
  }

  function edit(member: Member, access: MemberAccess) {
    setDrafts(previous => ({ ...previous, [member.id]: access }));
    setReview(null); setNotice(null);
    setRowErrors(previous => { const next = { ...previous }; delete next[member.id]; return next; });
  }

  async function save(member: Member, confirmedAccess?: MemberAccess) {
    if (!currentSession() || busyId || loading || denied || member.id === identity.sub) return;
    const access = drafts[member.id];
    const invalid = validateMemberAccess(access);
    if (invalid) { setRowErrors(previous => ({ ...previous, [member.id]: invalid })); return; }
    if (confirmedAccess && !sameMemberAccess(access, confirmedAccess)) {
      setReview(null); setRowErrors(previous => ({ ...previous, [member.id]: 'Drepturile s-au schimbat. Verifică din nou modificarea.' })); return;
    }
    if (!confirmedAccess && addsPrivilegedRole(member, access)) {
      setReview({ id: member.id, access: { roles: [...access.roles], department: access.department } }); return;
    }
    ++sequence.current;
    setBusyId(member.id); setError(null); setNotice(null); setReview(null);
    try {
      const updated = await updateMemberAccess(member.id, access);
      if (!currentSession()) return;
      setMembers(previous => previous.map(item => item.id === updated.id ? updated : item));
      setDrafts(previous => ({ ...previous, [updated.id]: accessOf(updated) }));
      setNotice(`Drepturile pentru ${updated.username} au fost salvate. Membrul trebuie să se autentifice din nou pentru un token cu noile drepturi.`);
    } catch (problem) {
      if (!currentSession()) return;
      setRowErrors(previous => ({ ...previous, [member.id]: messageOf(problem) }));
      if (problem instanceof ApiError && problem.status === 403) {
        setDenied(true); setError(messageOf(problem)); setMembers([]); setDrafts({});
      }
    } finally { if (currentSession()) setBusyId(null); }
  }

  return <section className="section members-section" aria-labelledby="members-title" aria-busy={loading}>
    <div className="section-heading"><h2 id="members-title">Administrare membri</h2><button className="secondary" disabled={loading || Boolean(busyId)} onClick={() => navigate({ search, page })}>Actualizează lista</button></div>
    <p className="muted">Aici le dai conturilor roluri și departamente. USER înseamnă acces de membru, ADMIN poate gestiona toate documentele, IMPLEMENTATOR poate schimba drepturile celorlalți.</p>
    <p className="small muted">Drepturile sunt verificate și de API. Modificările se aplică în tokenul obținut la următoarea autentificare a membrului; documentele deja încărcate își păstrează proprietarul și departamentul.</p>
    <form className="members-search" onSubmit={searchMembers}><label>Caută după utilizator<input type="search" name="member-search" maxLength={80} value={searchText} onChange={event => setSearchText(event.target.value)} disabled={Boolean(busyId)} placeholder="Ex. alice.it" /></label><button type="submit" disabled={loading || Boolean(busyId)}>Caută</button></form>
    {pendingNavigation && <div className="notice info" role="group" aria-label="Modificări nesalvate"><p>Ai modificări nesalvate. Continui și renunți la ele?</p><div className="button-row"><button onClick={() => navigate(pendingNavigation, true)}>Renunță la modificări și continuă</button><button className="secondary" onClick={() => setPendingNavigation(null)}>Rămâi pe pagină</button></div></div>}
    {error && <div className="notice error" role="alert"><p>{error}</p>{denied && <button className="secondary" onClick={() => void auth.login()}>Actualizează autentificarea</button>}</div>}
    <div aria-live="polite">{notice && <p className="notice success">{notice}</p>}</div>
    {loading ? <p role="status">Caut membrii…</p> : !loaded ? <p className="muted">Lista nu a putut fi încărcată. Folosește „Actualizează lista” pentru a reîncerca.</p> : members.length === 0 && !denied ? <p className="muted">Nu am găsit niciun membru cu căutarea asta.</p> : <ul className="members-list">{members.map(member => {
      const access = drafts[member.id] || accessOf(member);
      const self = member.id === identity.sub;
      const disabled = loading || Boolean(busyId) || self || denied;
      const changed = !sameMemberAccess(member, access);
      return <li key={member.id} className="member-card">
        <div className="member-heading"><div><h3>{member.username}</h3><p className="small muted">{member.enabled ? 'Cont activ' : 'Cont dezactivat'}{self ? ' · Contul tău este protejat' : ''}</p></div><span className="tag">{member.roles.join(', ') || 'Fără rol'}</span></div>
        <fieldset className="member-roles" disabled={disabled}><legend>Roluri pentru {member.username}</legend>{MEMBER_ROLES.map(role => <label key={role} className="checkbox-label"><input type="checkbox" aria-label={`${role} pentru ${member.username}`} checked={access.roles.includes(role)} onChange={event => edit(member, { ...access, roles: event.target.checked ? [...access.roles, role] : access.roles.filter(value => value !== role) })} />{role}</label>)}</fieldset>
        <div className="member-controls"><label>Departament pentru {member.username}<select value={access.department} disabled={disabled} onChange={event => edit(member, { ...access, department: event.target.value })}>{!MEMBER_DEPARTMENTS.includes(access.department) && <option value="">Selectează departamentul</option>}{MEMBER_DEPARTMENTS.map(department => <option key={department} value={department}>{department}</option>)}</select></label><button disabled={disabled || !changed} onClick={() => void save(member)}>{busyId === member.id ? 'Se salvează…' : `Salvează pentru ${member.username}`}</button></div>
        {self && <p className="small muted">Rolurile și departamentul contului curent sunt protejate pentru a păstra accesul la administrare.</p>}
        {rowErrors[member.id] && <p className="notice error" role="alert">{rowErrors[member.id]}</p>}
        {review?.id === member.id && <div className="notice info" role="group" aria-label={`Confirmă drepturile pentru ${member.username}`}><p><strong>Confirmi drepturile pentru {member.username}?</strong></p><p>Roluri: {review.access.roles.join(', ')}. Departament: {review.access.department}. ADMIN poate accesa și șterge toate documentele. IMPLEMENTATOR poate administra accesul membrilor.</p><div className="button-row"><button disabled={Boolean(busyId)} onClick={() => void save(member, review.access)}>Confirmă modificarea</button><button className="secondary" onClick={() => setReview(null)}>Anulează</button></div></div>}
      </li>;
    })}</ul>}
    <div className="members-pagination" aria-label="Paginarea membrilor"><button className="secondary" disabled={loading || Boolean(busyId) || page === 0 || denied} onClick={() => navigate({ search, page: page - 1 })}>Pagina anterioară</button><span>Pagina {page + 1}</span><button className="secondary" disabled={loading || Boolean(busyId) || !hasMore || denied} onClick={() => navigate({ search, page: page + 1 })}>Pagina următoare</button></div>
  </section>;
}
