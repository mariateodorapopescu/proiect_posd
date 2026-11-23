import { useEffect, useRef, useState } from 'react';
import { auth } from './auth';
import { config } from './config';
import type { Identity } from './api';
import { CONFIRMATIONS, PROBE_INTERVAL_MS, finishAtExpiry, nearExpiry, observe, startMonitor, stopMonitor } from './monitor-policy.mjs';

type Monitor = ReturnType<typeof startMonitor>;
const SYMBOLS: Record<string, string> = { allowed: '\u2713', denied: '\u2715', expired: '\u2715', unreachable: '!', error: '!' };
const LABELS: Record<string, string> = { allowed: 'acceptat', denied: 'refuzat', expired: 'refuzat după expirare', unreachable: 'fără răspuns', error: 'eroare de server' };
const seconds = (milliseconds: number) => Math.round(milliseconds / 1000);

// The monitor deliberately bypasses request(): a 401 there signs the user out, and here the
// point is to keep sending the same token and watch when the API stops accepting it.
async function probe(token: string, outer: AbortSignal): Promise<number> {
  const request = new AbortController();
  const cancel = () => request.abort();
  outer.addEventListener('abort', cancel);
  const timer = window.setTimeout(cancel, 5000);
  try {
    const response = await fetch(`${config.apiUrl}/api/me`, { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store', credentials: 'omit', signal: request.signal });
    return response.status;
  } catch { return 0; }
  finally { window.clearTimeout(timer); outer.removeEventListener('abort', cancel); }
}

function pause(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>(resolve => {
    const done = () => { window.clearTimeout(timer); signal.removeEventListener('abort', done); resolve(); };
    const timer = window.setTimeout(done, milliseconds);
    signal.addEventListener('abort', done);
  });
}

function describe(monitor: Monitor): { tone: 'info' | 'success' | 'error'; text: string } {
  const verdict = monitor.verdict;
  if (monitor.phase === 'running') return { tone: 'info', text: `Se monitorizează: ${monitor.total} cereri trimise, ${monitor.allowed} acceptate.` };
  if (monitor.phase === 'stopped') return { tone: 'info', text: `Monitorizare oprită după ${monitor.total} cereri.` };
  if (verdict?.kind === 'revoked') return { tone: 'error', text: `API-ul a început să refuze tokenul după ${seconds(verdict.afterMs)} s de monitorizare (HTTP ${verdict.status}), cu ${seconds(verdict.remainingMs)} s înainte de expirare. Tokenul era încă valabil, deci sesiunea a fost revocată sau drepturile au fost retrase.` };
  if (verdict?.kind === 'expired') return { tone: 'info', text: `API-ul a refuzat tokenul abia după expirare, la ${seconds(verdict.afterMs)} s de monitorizare.` };
  if (verdict?.kind === 'accepted_until_expiry') return { tone: 'success', text: `Tokenul a fost acceptat în toate cele ${verdict.requests} cereri până la expirare. Dacă sesiunea a fost revocată între timp, API-ul nu a observat asta înainte de expirare, ceea ce e așteptat la validarea locală a JWT.` };
  return { tone: 'info', text: 'Monitorizarea s-a încheiat înainte de a confirma un refuz.' };
}

export function RevocationMonitor({ identity }: { identity: Identity | null }) {
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const controller = useRef<AbortController | null>(null);
  const current = useRef<Monitor | null>(null);
  const expiresAt = auth.getSnapshot().user?.expires_at;
  const remaining = expiresAt ? Math.max(0, Math.ceil((expiresAt * 1000 - now) / 1000)) : null;
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 500); return () => window.clearInterval(timer); }, []);
  useEffect(() => () => controller.current?.abort(), []);

  function apply(update: (state: Monitor) => Monitor) {
    if (!current.current) return;
    current.current = update(current.current);
    setMonitor(current.current);
  }

  async function start() {
    const token = auth.token();
    const expires = auth.getSnapshot().user?.expires_at;
    if (!token || !expires) return;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    current.current = startMonitor(Date.now(), expires * 1000);
    setMonitor(current.current);
    while (!abort.signal.aborted && current.current?.phase === 'running') {
      const began = Date.now();
      if (nearExpiry(current.current, began)) { apply(finishAtExpiry); break; }
      const status = await probe(token, abort.signal);
      if (abort.signal.aborted) break;
      apply(state => observe(state, status, Date.now()));
      if (current.current?.phase !== 'running') break;
      await pause(Math.max(0, PROBE_INTERVAL_MS - (Date.now() - began)), abort.signal);
    }
  }

  function stop() { controller.current?.abort(); apply(stopMonitor); }

  const running = monitor?.phase === 'running';
  const summary = monitor ? describe(monitor) : null;
  return <section className="section monitor" aria-labelledby="monitor-title">
    <h2 id="monitor-title">Cât mai ține tokenul tău?</h2>
    <p className="muted">La fiecare secundă trimit API-ului o cerere cu tokenul tău și notez ce răspunde. Pagina nu află când se revocă sesiunea; vede doar când API-ul începe să refuze.</p>
    <dl className="monitor-stats">
      <div><dt>Strategie de validare</dt><dd>{identity?.strategy ?? '—'}</dd></div>
      <div><dt>Valabilitate rămasă</dt><dd>{remaining === null ? '—' : `${remaining} s`}</dd></div>
      <div><dt>Cereri trimise</dt><dd>{monitor?.total ?? 0}</dd></div>
    </dl>
    <div className="button-row">{running
      ? <button className="secondary" onClick={stop}>Oprește monitorizarea</button>
      : <button onClick={() => void start()} disabled={remaining === null || remaining < 3}>{monitor ? 'Repornește monitorizarea' : 'Pornește monitorizarea'}</button>}</div>
    <ol className="monitor-steps">
      <li>Pornește monitorizarea.</li>
      <li>Închide sesiunea în alt tab: apasă „Deconectare SSO” în Documente sau revocă sesiunea din consola Keycloak.</li>
      <li>Urmărește răspunsurile. Cu introspecție, refuzul apare imediat, după {CONFIRMATIONS} refuzuri consecutive. Cu validare locală JWT, tokenul rămâne acceptat până expiră.</li>
    </ol>
    {monitor && monitor.events.length > 0 && <ol className="probe-strip" aria-label="Răspunsurile API-ului, în ordine cronologică">{monitor.events.map(event => <li key={event.atMs} className={`probe ${event.kind}`} title={`HTTP ${event.status || '—'} · ${seconds(event.atMs - monitor.startedAtMs)} s`}><span aria-hidden="true">{SYMBOLS[event.kind]}</span><span className="sr-only">{`${seconds(event.atMs - monitor.startedAtMs)} s: ${LABELS[event.kind]}`}</span></li>)}</ol>}
    <div aria-live="polite">{summary && <p className={`notice ${summary.tone}`}>{summary.text}</p>}</div>
  </section>;
}
