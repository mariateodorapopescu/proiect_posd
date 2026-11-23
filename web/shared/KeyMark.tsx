/** Cheia din siglă: un contur simplu, desenat cu linie, care ia culoarea textului din jur. */
export function KeyMark({ className }: { className?: string }) {
  return <svg className={className} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    <circle cx="10" cy="10" r="6" />
    <path d="M14.5 14.5 28 28M22.5 22.5l3-3M26 26l3-3" />
  </svg>;
}
