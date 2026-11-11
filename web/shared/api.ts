import { auth } from './auth';
import { config } from './config';
import { errorMessage, isCurrentSession } from './policy.mjs';

export type DocumentInfo = { id: number; title: string; originalFilename: string; ownerId: string; department: string; size: number; createdAt: string };
export type Identity = { sub: string; username: string; department: string; roles: string[]; scopes: string[]; strategy: string };
export type Member = { id: string; username: string; department: string; roles: string[]; enabled: boolean };
export type MemberAccess = { roles: string[]; department: string };
export type MemberPage = { members: Member[]; page: number; hasMore: boolean };
export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message); }
}

export async function request(path: string, init: RequestInit = {}, authenticated = true): Promise<Response> {
  const token = auth.token();
  if (authenticated && !token) throw new ApiError(401, errorMessage(401));
  const headers = new Headers(init.headers);
  if (authenticated) headers.set('Authorization', `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${config.apiUrl}${path}`, { ...init, headers, signal: init.signal ?? AbortSignal.timeout(30000), cache: 'no-store', credentials: 'omit' });
  } catch { throw new ApiError(0, errorMessage(0)); }
  if (authenticated && !isCurrentSession(token, auth.token())) throw new ApiError(0, 'Sesiunea s-a schimbat. Cererea a fost ignorată.');
  if (!response.ok) {
    let message: unknown;
    try { message = (await response.json()).message; } catch { /* A proxy may return a non-JSON error. */ }
    if (response.status === 401 && token && authenticated) await auth.rejectToken(token);
    throw new ApiError(response.status, errorMessage(response.status, message));
  }
  return response;
}

export async function loadIdentity(): Promise<Identity> { return (await request('/api/me')).json(); }
export async function listDocuments(): Promise<DocumentInfo[]> { return (await request('/api/documents')).json(); }
export async function uploadDocument(title: string, file: File): Promise<void> {
  const form = new FormData(); form.set('title', title); form.set('file', file);
  await request('/api/documents', { method: 'POST', body: form });
}
export async function deleteDocument(id: number): Promise<void> { await request(`/api/documents/${id}`, { method: 'DELETE' }); }
export async function listMembers(search: string, page: number, signal?: AbortSignal): Promise<MemberPage> {
  const query = new URLSearchParams({ search, page: String(page) });
  return (await request(`/api/members?${query}`, { signal })).json();
}
export async function updateMemberAccess(id: string, access: MemberAccess): Promise<Member> {
  return (await request(`/api/members/${encodeURIComponent(id)}/access`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(access)
  })).json();
}
export async function downloadDocument(document: DocumentInfo): Promise<void> {
  const sessionToken = auth.token();
  const blob = await (await request(`/api/documents/${document.id}/download`)).blob();
  if (!isCurrentSession(sessionToken, auth.token())) throw new ApiError(0, 'Sesiunea s-a schimbat. Descărcarea a fost anulată.');
  const url = URL.createObjectURL(blob);
  const anchor = window.document.createElement('a');
  anchor.href = url; anchor.download = document.originalFilename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
