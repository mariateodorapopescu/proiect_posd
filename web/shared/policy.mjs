export function isCurrentSession(sentToken, currentToken) {
  return typeof sentToken === 'string' && sentToken.length > 0 && sentToken === currentToken;
}

export function callbackKind(search) {
  const params = new URLSearchParams(search);
  if (!params.has('state')) return null;
  return params.has('code') || params.has('error') ? 'signin' : 'signout';
}

export const TITLE_MAX_LENGTH = 160;

export function validateTitle(title) {
  if (typeof title !== 'string' || !title.trim() || title.trim().length > TITLE_MAX_LENGTH) {
    return `Titlul este obligatoriu și poate avea cel mult ${TITLE_MAX_LENGTH} de caractere.`;
  }
  return null;
}

export function validatePdf(file) {
  if (!file || file.size === 0) return 'Selectează un document PDF.';
  if (file.size > 10 * 1024 * 1024) return 'Fișierul poate avea cel mult 10 MiB.';
  if (file.type !== 'application/pdf' || !file.name.toLowerCase().endsWith('.pdf')) {
    return 'Selectează un fișier PDF cu extensia .pdf.';
  }
  return null;
}

export function errorMessage(status, serverMessage) {
  if (status === 401) return 'Sesiunea nu este validă sau tokenul a expirat. Autentifică-te din nou.';
  if (status === 403) return 'Acces refuzat. Verifică scope-ul, rolul și departamentul sau proprietarul documentului.';
  if (status === 404) return 'Documentul nu a fost găsit.';
  if (status === 413) return 'Fișierul depășește limita permisă de 10 MiB.';
  if (status >= 500) return 'Serviciul nu poate finaliza cererea. Încearcă din nou.';
  if (status >= 400 && typeof serverMessage === 'string' && serverMessage.trim()) return serverMessage.slice(0, 240);
  return 'Nu s-a putut conecta la API. Verifică dacă serviciile sunt pornite.';
}
