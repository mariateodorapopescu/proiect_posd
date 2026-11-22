import test from 'node:test';
import assert from 'node:assert/strict';
import { CONFIRMATIONS, MAX_EVENTS, STOP_BEFORE_EXPIRY_MS, classifyProbe, finishAtExpiry, nearExpiry, observe, startMonitor, stopMonitor } from '../shared/monitor-policy.mjs';

const EXPIRES = 60_000;
const run = (statuses, start = 0, step = 1000) => statuses.reduce((state, status, index) => observe(state, status, start + (index + 1) * step), startMonitor(start, EXPIRES));

test('probe statuses are classified relative to the token lifetime', () => {
  assert.equal(classifyProbe(200, EXPIRES, 1000), 'allowed');
  assert.equal(classifyProbe(401, EXPIRES, EXPIRES - 1), 'denied');
  assert.equal(classifyProbe(403, EXPIRES, EXPIRES - 1), 'denied');
  assert.equal(classifyProbe(401, EXPIRES, EXPIRES), 'expired');
  assert.equal(classifyProbe(0, EXPIRES, 1000), 'unreachable');
  assert.equal(classifyProbe(500, EXPIRES, 1000), 'error');
});

test('a denial before expiry is confirmed only after consecutive refusals and reads as revoked', () => {
  const state = run([200, 200, 401, 401, 401, 200]);
  assert.equal(state.phase, 'denied');
  assert.equal(state.total, 5, 'monitoring stops at the confirmation, later responses are ignored');
  assert.deepEqual(state.verdict, { kind: 'revoked', afterMs: 3000, remainingMs: EXPIRES - 3000, status: 401 });
});

test('a success resets the denial streak and the first-denial moment', () => {
  const state = run([401, 401, 200, 403, 403]);
  assert.equal(state.phase, 'running');
  assert.equal(state.streak, 2);
  assert.equal(state.firstDenial.atMs, 4000);
  assert.equal(CONFIRMATIONS, 3);
});

test('network and server errors neither confirm nor cancel a denial', () => {
  const state = run([401, 401, 0, 503, 401]);
  assert.equal(state.phase, 'denied');
  assert.equal(state.verdict.afterMs, 1000);
});

test('refusals after expiry are reported as expired, not revoked', () => {
  const state = [61_000, 62_000, 63_000].reduce((current, at) => observe(current, 401, at), startMonitor(0, EXPIRES));
  assert.equal(state.verdict.kind, 'expired');
  assert.equal(state.verdict.remainingMs, 0);
});

test('monitoring a token until just before expiry without refusals reports acceptance until expiry', () => {
  const state = finishAtExpiry(run([200, 200, 200]));
  assert.equal(state.phase, 'finished');
  assert.deepEqual(state.verdict, { kind: 'accepted_until_expiry', requests: 3 });
  assert.equal(nearExpiry(state, EXPIRES - STOP_BEFORE_EXPIRY_MS), true);
  assert.equal(nearExpiry(state, EXPIRES - STOP_BEFORE_EXPIRY_MS - 1), false);
});

test('an unconfirmed denial at the end is inconclusive and a stopped monitor does not change', () => {
  assert.deepEqual(finishAtExpiry(run([200, 401, 401])).verdict, { kind: 'inconclusive' });
  const stopped = stopMonitor(run([200]));
  assert.equal(stopped.phase, 'stopped');
  assert.equal(observe(stopped, 401, 9000), stopped);
  assert.equal(finishAtExpiry(stopped), stopped);
});

test('the event history is bounded and the counters keep the true total', () => {
  const statuses = Array.from({ length: MAX_EVENTS + 50 }, (_, index) => (index % 2 ? 0 : 200));
  const state = run(statuses, 0, 10);
  assert.equal(state.events.length, MAX_EVENTS);
  assert.equal(state.total, MAX_EVENTS + 50);
});
