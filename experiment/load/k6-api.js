// Scenariu k6 pentru costul validării tokenului sub încărcare.
//
// Se rulează din experiment/loadtest.py, care obține tokenul, pornește k6 și colectează
// `docker stats`. Tokenul vine DOAR din variabila de mediu SECURESYNC_ACCESS_TOKEN (nu din
// argumente CLI, ca să nu apară în lista de procese) și nu este scris nicăieri.
//
// Executorul constant-arrival-rate menține rata de cereri fixă, indiferent de latență:
// dacă API-ul nu ține pasul, k6 raportează `dropped_iterations` în loc să încetinească
// și să ascundă saturarea (problema „coordinated omission” a testelor în buclă închisă).
import http from 'k6/http';
import exec from 'k6/execution';
import { Counter, Trend } from 'k6/metrics';

const API_URL = (__ENV.API_URL || 'http://localhost:8081').replace(/\/+$/, '');
const ENDPOINT = __ENV.ENDPOINT || '/api/me';
const TOKEN = __ENV.SECURESYNC_ACCESS_TOKEN || '';
const RATE = Number(__ENV.RATE || 50);
const DURATION_S = Number(__ENV.DURATION || 30);
const SUMMARY_PATH = __ENV.SUMMARY_PATH || 'k6-summary.json';

if (!TOKEN) throw new Error('SECURESYNC_ACCESS_TOKEN lipsește');
if (!ENDPOINT.startsWith('/api/') || /[?#\\]|\.\./.test(ENDPOINT)) throw new Error('ENDPOINT invalid');

const status200 = new Counter('status_200');
const status401 = new Counter('status_401');
const status403 = new Counter('status_403');
const status5xx = new Counter('status_5xx');
const statusOther = new Counter('status_other');
// Secunda (de la începutul testului) în care apare fiecare 401/403: arată dacă refuzurile vin la
// început, la final (token expirat) sau dispersat (refuzuri sub încărcare).
const deniedAt = new Trend('t_denied_s');

export const options = {
  scenarios: {
    steady: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: `${DURATION_S}s`,
      preAllocatedVUs: Math.max(10, Math.ceil(RATE / 5)),
      maxVUs: Math.min(1000, Math.max(50, RATE * 2)),
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],

  discardResponseBodies: true,
};

// Doar 200 este „așteptat”; restul se numără în http_req_failed.
http.setResponseCallback(http.expectedStatuses(200));

export default function () {
  const response = http.get(`${API_URL}${ENDPOINT}`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
    redirects: 0,
  });
  const code = response.status;
  if (code === 401 || code === 403) {
    const at = exec.instance.currentTestRunDuration / 1000;
    deniedAt.add(at);
    // Câteva motive eșantionate (header-ul vine de la API și nu conține tokenul).
    if (Math.random() < 0.005) {
      console.log(`DENIED_REASON ${code} t=${at.toFixed(1)}s ${(response.headers['Www-Authenticate'] || '').slice(0, 160)}`);
    }
  }
  if (code === 200) status200.add(1);
  else if (code === 401) status401.add(1);
  else if (code === 403) status403.add(1);
  else if (code >= 500 || code === 0) status5xx.add(1);
  else statusOther.add(1);
}

const value = (data, metric, key) => (data.metrics[metric] && data.metrics[metric].values[key]) ?? null;

export function handleSummary(data) {
  const summary = {
    rate_target: RATE,
    duration_s: DURATION_S,
    requests: value(data, 'http_reqs', 'count'),
    rps: value(data, 'http_reqs', 'rate'),
    failed_ratio: value(data, 'http_req_failed', 'rate'),
    dropped_iterations: value(data, 'dropped_iterations', 'count') ?? 0,
    latency_ms: {
      avg: value(data, 'http_req_duration', 'avg'),
      p50: value(data, 'http_req_duration', 'med'),
      p90: value(data, 'http_req_duration', 'p(90)'),
      p95: value(data, 'http_req_duration', 'p(95)'),
      p99: value(data, 'http_req_duration', 'p(99)'),
      max: value(data, 'http_req_duration', 'max'),
    },
    denied_at_s: data.metrics.t_denied_s ? {
      count: value(data, 't_denied_s', 'count') ?? null,
      min: value(data, 't_denied_s', 'min'),
      med: value(data, 't_denied_s', 'med'),
      max: value(data, 't_denied_s', 'max'),
    } : null,
    statuses: {
      '200': value(data, 'status_200', 'count') ?? 0,
      '401': value(data, 'status_401', 'count') ?? 0,
      '403': value(data, 'status_403', 'count') ?? 0,
      '5xx': value(data, 'status_5xx', 'count') ?? 0,
      other: value(data, 'status_other', 'count') ?? 0,
    },
  };
  return { [SUMMARY_PATH]: JSON.stringify(summary, null, 2) };
}
