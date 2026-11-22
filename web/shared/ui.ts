export const messageOf = (error: unknown) => error instanceof Error ? error.message : 'Cererea nu a putut fi finalizată.';
export const dateFormat = new Intl.DateTimeFormat('ro-RO', { dateStyle: 'medium', timeStyle: 'short' });
