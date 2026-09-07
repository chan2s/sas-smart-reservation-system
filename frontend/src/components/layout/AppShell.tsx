import { Outlet } from 'react-router-dom'
import { Header, MobileBottomNav } from './Header'

/**
 * Application shell.
 *
 * Layout model (no sidebar — full-width top navigation):
 *
 *   ┌──────────────────────────────────────────┐
 *   │  Header (sticky, stays while scrolling)  │
 *   ├──────────────────────────────────────────┤
 *   │  Main — document scroll, full viewport   │
 *   │  width, max-w container, generous pad    │
 *   └──────────────────────────────────────────┘
 *
 * The shell is a plain flex column: the header is `sticky top-0`, and the
 * document scrolls naturally. The sticky wizard footer (`bottom-0` in
 * ReservationWizardPage) keeps working because the scroll container is now
 * the viewport, and its bottom clearance is handled by main's pb-24 on
 * mobile (which also clears the fixed bottom nav).
 */
export function AppShell() {
  return (
    <div className="flex min-h-dvh flex-col bg-soft">
      <Header />

      <main className="w-full flex-1">
        {/* Comfortable max content width — never overly wide on large monitors */}
        <div className="mx-auto w-full max-w-[1440px] px-4 pb-24 pt-8 sm:px-6 lg:px-10 lg:pb-14 lg:pt-10">
          <Outlet />
        </div>
      </main>

      <MobileBottomNav />
    </div>
  )
}
