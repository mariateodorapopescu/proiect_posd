export const MEMBER_ROLES = ['USER', 'ADMIN', 'IMPLEMENTATOR'];
export const MEMBER_DEPARTMENTS = ['IT', 'HR'];

export function mayManageMembers(identity) {
  return Boolean(identity?.roles?.includes('IMPLEMENTATOR') && identity?.scopes?.includes('members:manage'));
}

export function validateMemberAccess(access) {
  if (!Array.isArray(access?.roles) || access.roles.length === 0 ||
      new Set(access.roles).size !== access.roles.length || access.roles.some(role => !MEMBER_ROLES.includes(role))) {
    return 'Selectează cel puțin un rol dintre USER, ADMIN și IMPLEMENTATOR.';
  }
  if (!MEMBER_DEPARTMENTS.includes(access.department)) return 'Selectează departamentul IT sau HR.';
  return null;
}

export function sameMemberAccess(left, right) {
  return left.department === right.department && left.roles.length === right.roles.length &&
    left.roles.every(role => right.roles.includes(role));
}

export function addsPrivilegedRole(previous, next) {
  return ['ADMIN', 'IMPLEMENTATOR'].some(role => next.roles.includes(role) && !previous.roles.includes(role));
}

export function membersErrorMessage(status) {
  if (status === 403) return 'Accesul la administrarea membrilor a fost refuzat. Verifică rolul IMPLEMENTATOR și autentifică-te din nou.';
  if (status === 503 || status >= 500) return 'Serviciul de administrare nu este disponibil. Actualizează lista înainte de a reîncerca; verifică drepturile afișate dacă modificarea a fost întreruptă.';
  if (status === 400) return 'Verifică rolurile, departamentul și textul de căutare.';
  if (status === 404) return 'Membrul nu mai este disponibil. Actualizează lista.';
  if (status === 409) return 'Contul este protejat sau a fost modificat între timp. Actualizează lista.';
  return null;
}
