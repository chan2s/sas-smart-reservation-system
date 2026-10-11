/**
 * Google-branded OAuth button. Shared by the login and registration pages so
 * both start the exact same backend flow (`/api/auth/google/start/`) with the
 * exact same styling — there is only one OAuth implementation.
 */
interface GoogleAuthButtonProps {
  onClick: () => void
  loading?: boolean
  disabled?: boolean
  /** Shown while the browser is being sent to Google's consent screen. */
  loadingLabel?: string
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-[18px]" aria-hidden>
      <path
        fill="#4285F4"
        d="M23.5 12.27c0-.85-.08-1.66-.22-2.45H12v4.64h6.45a5.52 5.52 0 0 1-2.4 3.62v3h3.87c2.26-2.09 3.58-5.16 3.58-8.81Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.87-3c-1.08.72-2.45 1.15-4.07 1.15-3.13 0-5.78-2.11-6.73-4.96H1.29v3.1A12 12 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.27 14.28a7.2 7.2 0 0 1 0-4.56v-3.1H1.29a12 12 0 0 0 0 10.76l3.98-3.1Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.76c1.76 0 3.34.6 4.58 1.8l3.44-3.44A11.97 11.97 0 0 0 12 0 12 12 0 0 0 1.29 6.62l3.98 3.1C6.22 6.87 8.87 4.76 12 4.76Z"
      />
    </svg>
  )
}

export function GoogleAuthButton({
  onClick,
  loading = false,
  disabled = false,
  loadingLabel = 'Redirecting to Google…',
}: GoogleAuthButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      className="flex w-full items-center justify-center gap-2.5 rounded-full border border-line bg-surface px-4 py-3 text-sm font-medium text-ink shadow-sm transition-colors duration-150 hover:bg-soft disabled:opacity-60"
    >
      <GoogleIcon />
      {loading ? loadingLabel : 'Continue with Google'}
    </button>
  )
}
