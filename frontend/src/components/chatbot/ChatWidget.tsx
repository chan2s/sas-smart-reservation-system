import { useEffect, useRef, useState } from 'react'
import { Bot, SendHorizonal, Trash2, X } from 'lucide-react'
import { Spinner } from '@/components/ui/Misc'
import { useAuth } from '@/hooks/useAuth'
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
 *
 * The starter suggestions are generated conditionally from the existing
 * auth context: unauthenticated visitors (landing, login, register pages)
 * get non-personalized public-information questions, while signed-in users
 * get personalized requester questions. Personal data itself is always
 * resolved server-side by the pipeline.
 *
 * Conversations live only in this component's state (the backend keeps an
 * append-only diagnostic ChatLog, not readable transcripts), so deleting a
 * message or clearing the whole conversation changes local state only — it
 * never touches reservations, knowledge-base entries, or any other server
 * data.
 */

interface ChatEntry {
  id: number
  role: 'user' | 'bot'
  text: string
  meta?: { intent?: string; source?: string }
  suggestions?: ChatbotSuggestion[]
}

let entryId = 0

// Non-personalized starter questions for public visitors. Never phrased
// with "I/my/me/mine" — a visitor may not have an account at all.
const PUBLIC_SUGGESTIONS = [
  'What is SAS Reserve?',
  'What facilities can be reserved?',
  'How does the reservation process work?',
  'What are the reservation rules?',
]

// Personalized starter questions for signed-in requesters.
const REQUESTER_SUGGESTIONS = [
  'What facilities are available tomorrow?',
  'What are my reservations?',
  'What is the status of my request?',
  'What is the cancellation policy?',
]

export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [entries, setEntries] = useState<ChatEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  // Message id awaiting delete confirmation (inline confirm, one at a time).
  const [deleteTargetId, setDeleteTargetId] = useState<number | null>(null)
  // Message id whose deletion failed — shows a non-blocking inline notice.
  const [deleteErrorId, setDeleteErrorId] = useState<number | null>(null)
  // Header clear-conversation confirmation (small popover, one at a time).
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false)
  const { user } = useAuth()
  const { mutate, isPending } = useChatbot()
  const suggestions = user ? REQUESTER_SUGGESTIONS : PUBLIC_SUGGESTIONS
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

  const requestDelete = (id: number) => {
    setDeleteErrorId(null)
    setDeleteTargetId(id)
    // Only one destructive confirmation can be open at a time.
    setClearConfirmOpen(false)
  }

  const cancelDelete = () => setDeleteTargetId(null)

  // Conversations are local state, so deletion is a state update. The
  // try/catch keeps the failure contract honest: on any error the message
  // stays in the conversation and an inline notice is shown instead.
  const confirmDelete = (id: number) => {
    try {
      setEntries((prev) => prev.filter((entry) => entry.id !== id))
      setDeleteTargetId(null)
      setDeleteErrorId(null)
    } catch {
      setDeleteTargetId(null)
      setDeleteErrorId(id)
    }
  }

  const requestClear = () => {
    // Only one destructive confirmation can be open at a time.
    setDeleteTargetId(null)
    setClearConfirmOpen(true)
  }

  // Same local-state scope as message deletion: clears only this
  // component's conversation; nothing server-side is affected.
  const clearConversation = () => {
    setEntries([])
    setClearConfirmOpen(false)
    setDeleteTargetId(null)
    setDeleteErrorId(null)
    setError(null)
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
            <div className="flex items-center gap-1">
              {entries.length > 0 && (
                <div
                  className="relative"
                  onKeyDown={(event) => {
                    if (clearConfirmOpen && event.key === 'Escape') {
                      setClearConfirmOpen(false)
                    }
                  }}
                >
                  <button
                    type="button"
                    onClick={requestClear}
                    disabled={isPending}
                    className="rounded-lg p-1.5 text-muted transition-colors hover:bg-soft hover:text-ink disabled:pointer-events-none disabled:opacity-40"
                    aria-label="Clear conversation"
                  >
                    <Trash2 className="size-4" aria-hidden />
                  </button>
                  {/* Inline confirmation — anchored under the button so no
                      modal disrupts the chat. Escape cancels; focus starts
                      on Cancel so Enter cannot immediately destroy the
                      conversation. */}
                  {clearConfirmOpen && (
                    <div
                      className="absolute right-0 top-full z-10 mt-1.5 flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 shadow-float"
                      role="group"
                      aria-label="Clear conversation confirmation"
                    >
                      <span className="whitespace-nowrap text-xs font-medium text-ink">
                        Clear this conversation?
                      </span>
                      <button
                        type="button"
                        onClick={() => setClearConfirmOpen(false)}
                        autoFocus
                        className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-body transition-colors hover:bg-soft hover:text-ink"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={clearConversation}
                        className="rounded-md bg-status-rejected px-2.5 py-1.5 text-xs font-medium text-white transition-colors hover:bg-status-rejected/90"
                      >
                        Clear
                      </button>
                    </div>
                  )}
                </div>
              )}
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg p-1.5 text-muted transition-colors hover:bg-soft hover:text-ink"
                aria-label="Close assistant"
              >
                <X className="size-5" aria-hidden />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {entries.length === 0 && (
              <div className="space-y-3">
                <div className="rounded-2xl rounded-tl-sm border border-line bg-soft px-3.5 py-3 text-sm text-ink">
                  {user
                    ? 'Hi! Ask me about facility availability, your reservations, schedules, equipment, or policies. I answer only from this system\'s data.'
                    : 'Hi! Ask me about SAS Reserve — facilities, availability, schedules, equipment, or policies. Sign in to also ask about your own reservations.'}
                </div>
                <div className="flex flex-wrap gap-2 pt-1">
                  {suggestions.map((suggestion) => (
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
            {entries.map((entry) => {
              const confirming = deleteTargetId === entry.id
              return (
                <div
                  key={entry.id}
                  className={cn(
                    'group flex items-end gap-1',
                    entry.role === 'user' ? 'justify-end' : 'justify-start',
                  )}
                  onKeyDown={(event) => {
                    if (confirming && event.key === 'Escape') cancelDelete()
                  }}
                >
                  {entry.role === 'user' && <DeleteButton confirming={confirming} onRequest={() => requestDelete(entry.id)} />}
                  <div
                    className={cn(
                      'relative max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm',
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

                    {/* Inline confirmation — overlays the bubble so layout
                        never shifts. Escape cancels; focus starts on Cancel
                        so Enter cannot immediately destroy the message. */}
                    {confirming && (
                      <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-2xl border border-line bg-surface/95 px-2 text-ink">
                        <Trash2 className="size-3.5 shrink-0 text-status-rejected" aria-hidden />
                        <span className="text-xs font-medium">Delete this message?</span>
                        <button
                          type="button"
                          onClick={cancelDelete}
                          autoFocus
                          className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-body transition-colors hover:bg-soft hover:text-ink"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => confirmDelete(entry.id)}
                          className="rounded-md bg-status-rejected px-2.5 py-1.5 text-xs font-medium text-white transition-colors hover:bg-status-rejected/90"
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                  {entry.role === 'bot' && <DeleteButton confirming={confirming} onRequest={() => requestDelete(entry.id)} />}
                  {deleteErrorId === entry.id && (
                    <p className="w-full text-xs text-status-rejected" role="status">
                      Unable to delete this message. Please try again.
                    </p>
                  )}
                </div>
              )
            })}
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
                placeholder={user ? 'Ask about facilities, reservations…' : 'Ask about SAS Reserve…'}
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

/**
 * Subtle per-message delete trigger.
 *
 * Always rendered as a flex sibling outside the bubble, so revealing it
 * never reflows the message text. Hidden on desktop until hover (or
 * keyboard focus), always visible on touch devices where hover does not
 * exist. size-7 (28px) keeps the touch target usable on mobile.
 */
function DeleteButton({ confirming, onRequest }: { confirming: boolean; onRequest: () => void }) {
  return (
    <button
      type="button"
      onClick={onRequest}
      disabled={confirming}
      className={cn(
        'mb-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg text-muted transition-opacity',
        'hover:bg-soft hover:text-ink focus:outline-none focus:ring-2 focus:ring-brand/40',
        'focus:opacity-100 disabled:pointer-events-none disabled:opacity-0',
        'sm:opacity-0 sm:focus:opacity-100 sm:group-hover:opacity-100',
      )}
      aria-label="Delete message"
    >
      <Trash2 className="size-3.5" aria-hidden />
    </button>
  )
}
