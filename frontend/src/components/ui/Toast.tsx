import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { CheckCircle2, Info, X, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

type ToastTone = 'success' | 'error' | 'info'
interface ToastItem {
  id: number
  tone: ToastTone
  message: string
}

interface ToastContextValue {
  toast: (message: string, tone?: ToastTone) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: number) => {
    setToasts((items) => items.filter((item) => item.id !== id))
  }, [])

  const toast = useCallback(
    (message: string, tone: ToastTone = 'success') => {
      const id = nextId++
      setToasts((items) => [...items, { id, tone, message }])
      window.setTimeout(() => dismiss(id), 4200)
    },
    [dismiss],
  )

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2"
        aria-live="polite"
      >
        {toasts.map((item) => (
          <div
            key={item.id}
            className={cn(
              'pointer-events-auto flex items-start gap-3 rounded-xl border bg-surface p-3.5 shadow-pop animate-fade-up',
              item.tone === 'success' && 'border-status-available/20',
              item.tone === 'error' && 'border-status-rejected/20',
              item.tone === 'info' && 'border-brand/20',
            )}
          >
            {item.tone === 'success' && (
              <CheckCircle2 className="mt-0.5 size-4.5 shrink-0 text-status-available" />
            )}
            {item.tone === 'error' && (
              <XCircle className="mt-0.5 size-4.5 shrink-0 text-status-rejected" />
            )}
            {item.tone === 'info' && (
              <Info className="mt-0.5 size-4.5 shrink-0 text-brand" />
            )}
            <p className="flex-1 text-sm leading-snug text-ink">{item.message}</p>
            <button
              onClick={() => dismiss(item.id)}
              className="rounded p-0.5 text-muted transition-colors hover:text-ink"
              aria-label="Dismiss notification"
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used within ToastProvider')
  return context
}