import { useEffect, useRef, useState } from 'react'
import { Bot, SendHorizonal, X } from 'lucide-react'
import { Spinner } from '@/components/ui/Misc'
import { useChatbot } from '@/hooks/queries'
import type { ChatbotResponse, ChatbotSuggestion } from '@/lib/types'
import { cn } from '@/lib/utils'

/**
 * Floating chat assistant.
 *
 * A thin client over POST /api/chatbot: it renders whatever the backend's
 * rule-based pipeline returns and never contains business logic. Answers
 * are grounded in the live database on the server; the widget only manages
 * conversation display.
 */

interface ChatEntry {
  id: number
  role: 'user' | 'bot'
  text: string
  meta?: { intent?: string; source?: string }
  suggestions?: ChatbotSuggestion[]
}

let entryId = 0

const SUGGESTIONS = [
  'What facilities are available tomorrow?',
  'Show my reservations',
  'What is the cancellation policy?',
]

export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [entries, setEntries] = useState<ChatEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const { mutate, isPending } = useChatbot()
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Scroll to the newest message whenever the conversation grows.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [entries, isPending])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const send = (raw: string) => {
    const message = raw.trim()
    if (!message || isPending) return
    setError(null)
    setDraft('')
    setEntries((prev) => [...prev, { id: ++entryId, role: 'user', text: message }])
    mutate(message, {
      onSuccess: (response: ChatbotResponse) => {
        setEntries((prev) => [
          ...prev,
          {
            id: ++entryId,
            role: 'bot',
            text: response.message,
            meta: { intent: response.intent, source: response.source },
            suggestions: response.suggestions ?? [],
          },
        ])
      },
      onError: () => {
        setError('The system is currently unable to retrieve the latest information. Please try again later.')
      },
    })
  }

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      send(draft)
    }
  }

  return (
    <>
      {/* Launcher — sits above the mobile bottom nav */}
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-20 right-4 z-40 flex size-14 items-center justify-center rounded-full bg-brand text-white shadow-float transition-transform duration-150 hover:scale-105 hover:bg-brand-dark lg:bottom-6 lg:right-6"
          aria-label="Open assistant"
        >
          <Bot className="size-6" aria-hidden />
        </button>
      )}

      {/* Panel */}
      {open && (
        <div
          className={cn(
            'fixed z-40 flex flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-float',
            // Mobile: near-fullscreen sheet above the bottom nav.
            'inset-x-3 bottom-16 top-16 sm:inset-x-auto sm:bottom-6 sm:right-6 sm:top-auto sm:h-[560px] sm:w-[380px]',
          )}
          role="dialog"
          aria-label="SAS Reserve assistant"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-line bg-surface px-4 py-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand text-white">
                <Bot className="size-5" aria-hidden />
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-ink">SAS Reserve Assistant</p>
                <p className="text-[11px] text-muted">Answers from live system data</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-lg p-1.5 text-muted transition-colors hover:bg-soft hover:text-ink"
              aria-label="Close assistant"
            >
              <X className="size-5" aria-hidden />
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {entries.length === 0 && (
              <div className="space-y-3">
                <div className="rounded-2xl rounded-tl-sm border border-line bg-soft px-3.5 py-3 text-sm text-ink">
                  Hi! Ask me about facility availability, your reservations, schedules, equipment, or policies. I answer only from this system's data.
                </div>
                <div className="flex flex-wrap gap-2 pt-1">
                  {SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => send(suggestion)}
                      className="rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium text-body transition-colors hover:border-brand hover:text-brand"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {entries.map((entry) => (
              <div
                key={entry.id}
                className={cn('flex', entry.role === 'user' ? 'justify-end' : 'justify-start')}
              >
                <div
                  className={cn(
                    'max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm',
                    entry.role === 'user'
                      ? 'rounded-br-sm bg-brand text-white'
                      : 'rounded-tl-sm border border-line bg-soft text-ink',
                  )}
                >
                  {entry.text}
                  {entry.meta?.source === 'fallback' && entry.role === 'bot' && (
                    <span className="mt-1 block text-[10px] uppercase tracking-wide text-muted">
                      not found in system
                    </span>
                  )}
                  {entry.role === 'bot' && !!entry.suggestions?.length && (
                    <div className="mt-2.5 border-t border-line/70 pt-2.5">
                      <p className="text-[10px] font-medium uppercase tracking-wide text-muted">
                        You may also ask
                      </p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {entry.suggestions.map((suggestion) => (
                          <button
                            key={suggestion.action + suggestion.text}
                            type="button"
                            onClick={() => send(suggestion.text)}
                            className="rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium text-body transition-colors hover:border-brand hover:text-brand"
                          >
                            {suggestion.text}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isPending && (
              <div className="flex justify-start">
                <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm border border-line bg-soft px-3.5 py-2.5 text-sm text-muted">
                  <Spinner className="size-4" />
                  Checking the system…
                </div>
              </div>
            )}
            {error && (
              <div className="rounded-xl border border-status-rejected/40 bg-status-rejected-bg px-3.5 py-2.5 text-sm text-status-rejected">
                {error}
              </div>
            )}
          </div>

          {/* Input */}
          <div className="border-t border-line bg-surface p-3">
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={onKeyDown}
                rows={1}
                placeholder="Ask about facilities, reservations…"
                className="max-h-28 min-h-10 w-full resize-none rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-muted focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand/10"
                aria-label="Message"
              />
              <button
                type="button"
                onClick={() => send(draft)}
                disabled={!draft.trim() || isPending}
                className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-brand text-white transition-colors hover:bg-brand-dark disabled:cursor-not-allowed disabled:bg-brand/60"
                aria-label="Send message"
              >
                <SendHorizonal className="size-5" aria-hidden />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
