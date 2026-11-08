import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('@/components/chatbot/ChatWidget', () => ({
  ChatWidget: () => null,
}))

// ScrollTrigger touches window.matchMedia as soon as it is registered, which
// jsdom does not implement. Reduced motion means the component never calls
// into GSAP, so a minimal stub is enough.
vi.mock('gsap', () => ({
  default: { registerPlugin: vi.fn(), context: vi.fn(), fromTo: vi.fn() },
}))
vi.mock('gsap/ScrollTrigger', () => ({ ScrollTrigger: {} }))

import { AboutPage } from './AboutPage'

beforeEach(() => {
  // Reduced motion keeps the page's GSAP reveals inert in jsdom.
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  )
  vi.stubGlobal('scrollTo', vi.fn())
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderAbout() {
  return render(
    <MemoryRouter initialEntries={['/about']}>
      <Routes>
        <Route path="/about" element={<AboutPage />} />
        <Route path="/" element={<p>landing reached</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('AboutPage', () => {
  it('presents the project, capstone details, and developer credit', () => {
    renderAbout()

    expect(screen.getByRole('heading', { level: 1, name: 'SAS RESERVE' })).toBeInTheDocument()
    expect(
      screen.getByText(
        'A Smart Web-Based Facility and Resource Reservation System for NORSU-BSC',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'SAS Reserve is developed as an academic capstone project by Group 10. The project aims to improve reservation accessibility, operational efficiency, and resource management at NORSU-BSC through a centralized web-based reservation platform.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Our Capstone Project' })).toBeInTheDocument()
    expect(screen.getAllByText('Group 10').length).toBeGreaterThan(0)
    expect(
      screen.getByText('Negros Oriental State University – Bayawan-Sta. Catalina Campus'),
    ).toBeInTheDocument()
    expect(screen.getByText('Academic Capstone Project')).toBeInTheDocument()
    expect(screen.getByText('Cristian Paul Guillen')).toBeInTheDocument()
    expect(screen.getByText('Developer · Group 10 Capstone Project')).toBeInTheDocument()
  })

  it('links About Us from the desktop navigation and back to the landing page', () => {
    renderAbout()

    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getByRole('link', { name: 'About Us' })).toHaveAttribute('href', '/about')

    fireEvent.click(screen.getByRole('link', { name: 'Back to Home' }))
    expect(screen.getByText('landing reached')).toBeInTheDocument()
  })

  it('exposes About Us and a route home from the mobile menu', () => {
    renderAbout()

    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }))
    const menu = screen.getByRole('dialog', { name: 'Menu' })

    expect(within(menu).getByRole('link', { name: 'About Us' })).toHaveAttribute('href', '/about')
    expect(within(menu).getByRole('link', { name: 'Staff/Admin Login' })).toHaveAttribute(
      'href',
      '/login',
    )
    expect(within(menu).getByRole('link', { name: 'Create Reservation' })).toHaveAttribute(
      'href',
      '/reserve',
    )

    fireEvent.click(within(menu).getByRole('button', { name: 'Close menu' }))
    expect(screen.queryByRole('dialog', { name: 'Menu' })).toBeNull()
  })
})
