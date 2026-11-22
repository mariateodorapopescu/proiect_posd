// Pure state machine of the Portal revocation monitor. The monitor only observes API
// responses for one in-memory token; it never learns when a session was revoked.
/**
 * @typedef {{ atMs: number, status: number, kind: 'allowed' | 'denied' | 'expired' | 'unreachable' | 'error' }} ProbeEvent
 * @typedef {{ kind: 'revoked' | 'expired', afterMs: number, remainingMs: number, status: number }
 *   | { kind: 'accepted_until_expiry', requests: number } | { kind: 'inconclusive' }} Verdict
 * @typedef {{ phase: 'running' | 'denied' | 'finished' | 'stopped', startedAtMs: number, expiresAtMs: number,
 *   events: ProbeEvent[], total: number, allowed: number, streak: number, firstDenial: ProbeEvent | null,
 *   verdict: Verdict | null }} Monitor
 */
export const CONFIRMATIONS = 3;
export const MAX_EVENTS = 240;
export const PROBE_INTERVAL_MS = 1000;
export const STOP_BEFORE_EXPIRY_MS = 1500;

export function classifyProbe(status, expiresAtMs, nowMs) {
  if (status === 200) return 'allowed';
  if (status === 401 || status === 403) return nowMs < expiresAtMs ? 'denied' : 'expired';
  if (status === 0) return 'unreachable';
  return 'error';
}

/** @returns {Monitor} */
export function startMonitor(startedAtMs, expiresAtMs) {
  return { phase: 'running', startedAtMs, expiresAtMs, events: [], total: 0, allowed: 0, streak: 0, firstDenial: null, verdict: null };
}

// A denial counts only when CONFIRMATIONS consecutive 401/403 responses arrive; a 200 resets
// the streak, and network or server errors neither confirm nor cancel a denial.
/** @param {Monitor} state @param {number} status @param {number} atMs @returns {Monitor} */
export function observe(state, status, atMs) {
  if (state.phase !== 'running') return state;
  const kind = classifyProbe(status, state.expiresAtMs, atMs);
  const event = { atMs, status, kind };
  const denial = kind === 'denied' || kind === 'expired';
  const streak = denial ? state.streak + 1 : kind === 'allowed' ? 0 : state.streak;
  const firstDenial = denial ? (state.streak === 0 ? event : state.firstDenial) : kind === 'allowed' ? null : state.firstDenial;
  const next = {
    ...state, events: [...state.events, event].slice(-MAX_EVENTS), total: state.total + 1,
    allowed: state.allowed + (kind === 'allowed' ? 1 : 0), streak, firstDenial
  };
  if (streak < CONFIRMATIONS) return next;
  if (!firstDenial) return next;
  const remainingMs = Math.max(0, state.expiresAtMs - firstDenial.atMs);
  return {
    ...next, phase: 'denied',
    verdict: { kind: remainingMs > 0 ? 'revoked' : 'expired', afterMs: firstDenial.atMs - state.startedAtMs, remainingMs, status: firstDenial.status }
  };
}

/** @param {Monitor} state @param {number} nowMs */
export function nearExpiry(state, nowMs) {
  return nowMs >= state.expiresAtMs - STOP_BEFORE_EXPIRY_MS;
}

// Stop just before expiry: the application signs out when the token expires.
/** @param {Monitor} state @returns {Monitor} */
export function finishAtExpiry(state) {
  if (state.phase !== 'running') return state;
  return {
    ...state, phase: 'finished',
    verdict: state.streak > 0 ? { kind: 'inconclusive' } : { kind: 'accepted_until_expiry', requests: state.allowed }
  };
}

/** @param {Monitor} state @returns {Monitor} */
export function stopMonitor(state) {
  return state.phase === 'running' ? { ...state, phase: 'stopped' } : state;
}
