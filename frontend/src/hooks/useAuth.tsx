import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { api, consumeOAuthFragment, tokenStore } from '@/lib/api'
import { clearBackup } from '@/lib/offline/db'
import type { User } from '@/lib/types'

/** Remove any cached backup; never let a storage failure escape. */
function wipeOfflineBackup(): void {
  void clearBackup().catch(() => {
    /* storage unavailable — nothing to clear */
  })
}

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<User>
  logout: () => void
  updateUser: (user: User) => void
  isStaff: boolean
  /**
   * True for the designated approval-letter signatory (granted server-side by
   * an administrator). Only shapes the UI — the backend verifies every sign.
   */
  isApprovalSignatory: boolean
  /**
   * True for a non-administrator designated signatory, whose access is
   * limited to the Approval Letters module. The backend enforces the same
   * scope on every request; this only shapes navigation and route guards.
   */
  isApprovalLettersOnly: boolean
  /**
   * True while the signed-in account has not been approved by an
   * administrator: the interface must hide/disable every state-changing
   * action. Backend enforcement is authoritative — this only shapes the UI.
   */
  isViewOnly: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      // Google OAuth returns to /auth/callback with the JWT pair in the URL
      // fragment — consume it before anything else.
      const fromOAuth = consumeOAuthFragment()
      if (!fromOAuth && !tokenStore.access) {
        setLoading(false)
        return
      }
      try {
        const me = await api.me()
        if (!cancelled) setUser(me)
      } catch {
        tokenStore.clear()
        wipeOfflineBackup()
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  // A failed token refresh clears the stored tokens (see api.ts). Without
  // this, React state would keep a stale user and the UI would look logged
  // in while every request 401s — surfacing as bogus "no data" states.
  useEffect(() => {
    const onExpired = () => {
      tokenStore.clear()
      // Expired/cleared session: the cached backup must not outlive the user.
      wipeOfflineBackup()
      setUser(null)
    }
    window.addEventListener('sas:auth-expired', onExpired)
    return () => window.removeEventListener('sas:auth-expired', onExpired)
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const user = await api.login(username, password)
    setUser(user)
    return user
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
    // Security boundary: never leave one account's cached data on a shared
    // device after sign-out (covers account switching too).
    wipeOfflineBackup()
    setUser(null)
  }, [])

  const updateUser = useCallback((next: User) => setUser(next), [])

  const isApprovalSignatory = Boolean(
    user?.is_approval_signatory &&
      (user.role === 'ADMIN' || user.role === 'STAFF' ||
        user.role === 'ASSISTANT_CAMPUS_DIRECTOR_ADMIN_FINANCE'),
  )
  // The backend marks a non-administrator signatory as module-scoped. Fall
  // back to the same derivation so an older payload cannot expose the full
  // staff navigation to that account.
  const isApprovalLettersOnly = Boolean(
    isApprovalSignatory &&
      (user?.is_approval_letters_only ?? user?.role !== 'ADMIN'),
  )
  const isStaff = Boolean(
    (user?.role === 'ADMIN' || user?.role === 'STAFF') && !isApprovalLettersOnly,
  )

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        logout,
        updateUser,
        isStaff,
        isApprovalSignatory,
        isApprovalLettersOnly,
        isViewOnly: user?.is_view_only ?? false,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
