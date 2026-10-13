/**
 * Friendly copy for the `?google_error=…` codes the Django callback appends
 * when it redirects an OAuth failure back to the SPA. Shared by the login and
 * registration pages so both surfaces explain failures identically — the
 * backend is the single source of truth for the codes.
 */
export const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
  not_configured:
    'Google sign-in is not available right now. Please use your username and password.',
  invalid_state:
    'The sign-in request expired or was tampered with. Please try again.',
  cancelled: 'Google sign-in was cancelled.',
  missing_code: 'Google did not return an authorization code. Please try again.',
  token_exchange_failed: 'We could not verify your Google sign-in. Please try again.',
  identity_failed: 'We could not read your Google profile. Please try again.',
  email_unverified:
    'Your Google account email is not verified. Use a verified account or sign in with your password.',
  // "Continue with Google" on the registration page found an account that
  // already belongs to this Google identity.
  account_exists:
    'An account with this Google account already exists. Please log in instead.',
  // The Google-verified email already belongs to an email/password account.
  // It is never auto-linked; the user must sign in with their own credentials.
  email_registered:
    'An account with this email already exists. Please log in with your existing credentials instead.',
  // The account was deactivated by an administrator. Signing in never
  // reactivates it, so the user must ask the SAS office to restore access.
  account_deactivated:
    'This account has been deactivated. Please contact the SAS Office to restore access.',
}

/**
 * Codes that mean "you already have an account — send the user to log in".
 * The SPA renders these as a notice with a direct link to the login page
 * rather than a plain inline error.
 */
export const GOOGLE_LOGIN_REDIRECT_CODES = new Set(['account_exists', 'email_registered'])

/** The message for an error code, or a generic fallback. */
export function googleErrorMessage(code: string): string {
  return GOOGLE_ERROR_MESSAGES[code] ?? 'Google sign-in failed. Please try again.'
}
