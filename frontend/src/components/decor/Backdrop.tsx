/**
 * Decorative pastel shapes rendered behind page content.
 * They are aria-hidden and never receive pointer events, so they can't
 * interfere with text, buttons, or forms.
 */
export function Backdrop() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 -z-10 overflow-hidden"
    >
      <div className="absolute -right-32 -top-40 size-[420px] rounded-full bg-blob-indigo/50 blur-3xl" />
      <div className="absolute -left-40 top-1/3 size-[380px] rounded-full bg-blob-blue/40 blur-3xl" />
      <div className="absolute -bottom-48 right-1/4 size-[360px] rounded-full bg-blob-emerald/30 blur-3xl" />
    </div>
  )
}