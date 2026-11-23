import { useEffect, useRef, useState, type FormEvent } from 'react';
import { auth } from './auth';
import { deleteDocument, downloadDocument, listDocuments, uploadDocument, type DocumentInfo, type Identity } from './api';
import { TITLE_MAX_LENGTH, validatePdf, validateTitle } from './policy.mjs';
import { dateFormat, messageOf } from './ui';

export function Documents({ identity }: { identity: Identity | null }) {
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
      form.current?.reset(); setNotice('Gata, documentul e încărcat.'); await reload();
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
      <div className="section-heading"><h2 id="upload-title">Adaugă un document</h2><span className="tag">doar PDF, până la 10 MiB</span></div>
      <p className="muted">Îl văd cel care l-a încărcat, colegii din același departament și administratorii.</p>
      <form ref={form} onSubmit={upload} className="upload-form">
        <label>Titlu<input name="title" type="text" required maxLength={TITLE_MAX_LENGTH} placeholder="de ex. Ghid de lucru" disabled={busy || !mayWrite} /></label>
        <label>Fișier PDF<input ref={fileInput} name="file" type="file" accept="application/pdf,.pdf" required disabled={busy || !mayWrite} /></label>
        <button type="submit" disabled={busy || !mayWrite}>{busy ? 'Un moment…' : 'Încarcă PDF'}</button>
      </form>
      {identity && !mayWrite && <p className="muted">Contul acesta poate doar citi: nu are drept de încărcare.</p>}
    </section>
    <div aria-live="polite">{notice && <p className="notice success">{notice}</p>}</div>
    {error && <p className="notice error" role="alert">{error}</p>}
    <section className="section" aria-labelledby="documents-title" aria-busy={loading}>
      <div className="section-heading"><h2 id="documents-title">Ce poți citi acum</h2><button className="secondary" onClick={() => void reload()} disabled={loading || busy}>Actualizează</button></div>
      {loading ? <p className="muted" role="status">Caut documentele tale…</p> : !hasLoaded ? <p className="muted">Nu am putut încărca lista. Încearcă din nou cu „Actualizează”.</p> : documents.length === 0 ? <div className="empty"><span className="file-icon" aria-hidden="true">PDF</span><h3>Încă nu e nimic aici</h3><p className="muted">Adaugă primul PDF sau verifică dacă departamentul și drepturile contului sunt cele corecte.</p></div> : <ul className="document-list">{documents.map(document => {
        const canDelete = mayWrite && (identity?.sub === document.ownerId || identity?.roles.includes('ADMIN'));
        return <li key={document.id} className="document">
          <span className="file-icon" aria-hidden="true">PDF</span><div className="document-info"><h3>{document.title}</h3><p>{document.originalFilename} <span aria-hidden="true">·</span> {(document.size / 1024).toFixed(1)} KiB</p><p className="muted">{document.department} · {dateFormat.format(new Date(document.createdAt))}{identity?.sub === document.ownerId ? ' · Încărcat de tine' : ''}</p></div>
          <div className="document-actions"><button className="secondary" disabled={busy} onClick={() => void act(document, 'download')}>Descarcă</button>{canDelete && <button className="text danger" disabled={busy} onClick={() => setPendingDelete(document.id)}>Șterge</button>}</div>
          {pendingDelete === document.id && <div className="delete-confirm" role="group" aria-label={`Confirmă ștergerea ${document.title}`}><p>Îl ștergi definitiv? Nu se mai poate recupera.</p><button className="danger-button" disabled={busy} onClick={() => void act(document, 'delete')}>Da, șterge</button><button className="secondary" disabled={busy} onClick={() => setPendingDelete(null)}>Anulează</button></div>}
        </li>;
      })}</ul>}
    </section>
  </>;
}
