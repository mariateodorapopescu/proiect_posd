export const appKind = document.body.dataset.app === 'portal' ? 'portal' : 'documente';
export const config = {
  authority: import.meta.env.VITE_AUTHORITY || 'http://localhost:8080/realms/securesync',
  apiUrl: (import.meta.env.VITE_API_URL || 'http://localhost:8081').replace(/\/$/, ''),
  documenteUrl: import.meta.env.VITE_DOCUMENTE_URL || 'http://localhost:3001/',
  portalUrl: import.meta.env.VITE_PORTAL_URL || 'http://localhost:3002/',
  clientId: `securesync-${appKind}`,
  redirectUri: `${window.location.origin}/`
};
