import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { api, consumeOAuthFragment, tokenStore } from '@/lib/api'
import type { User } from '@/lib/types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<User>
  /** Completes a 2FA-challenged login with a TOTP or backup code. */
  verifyTwoFactorLogin: (mfaToken: string, code: string) => Promise<User>
  /** Completes first-time Google sign-in email OTP verification. */
  verifyGoogleOtp: (verificationToken: string, otp: string) => Promise<User>
  logout: () => void
  updateUser: (user: User) => void
  isStaff: boolean
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
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const user = await api.login(username, password)
    setUser(user)
    return user
  }, [])

  const verifyTwoFactorLogin = useCallback(async (mfaToken: string, code: string) => {
    const user = await api.verifyTwoFactorLogin(mfaToken, code)
    setUser(user)
    return user
  }, [])

  const verifyGoogleOtp = useCallback(async (verificationToken: string, otp: string) => {
    const user = await api.verifyGoogleOtp(verificationToken, otp)
    setUser(user)
    return user
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  const updateUser = useCallback((next: User) => setUser(next), [])

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        verifyTwoFactorLogin,
        verifyGoogleOtp,
        logout,
        updateUser,
        isStaff: user?.role === 'ADMIN' || user?.role === 'STAFF',
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