import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'

vi.mock('@/lib/api', () => ({
  // The real helper formats ApiError objects; these tests assert the dialog's
  // own behavior (fallback copy, inline error, pending gating).
  apiErrorMessage: (error: unknown, fallback: string) =>
    error instanceof Error && error.message ? error.message : fallback,
}))

import { ConfirmDialog } from './ConfirmDialog'

afterEach(cleanup)

/** Harness that lets each test drive the dialog like a real page does. */
function Harness({
  onConfirm,
  tone = 'danger',
}: {
  onConfirm: () => Promise<void>
  tone?: 'danger' | 'warning'
}) {
  const [open, setOpen] = useState(true)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open
      </button>
      <ConfirmDialog
        open={open}
        onClose={() => setOpen(false)}
        title="Remove resource?"
        description="This unassigns the equipment from this facility."
        recordName="Projector Set"
        tone={tone}
        confirmLabel="Remove resource"
        onConfirm={async () => {
          await onConfirm()
        }}
      />
    </>
  )
}

describe('ConfirmDialog', () => {
  it('renders title, description, and the affected record name', () => {
    render(<Harness onConfirm={vi.fn()} />)
    expect(screen.getByText('Remove resource?')).toBeTruthy()
    expect(
      screen.getByText('This unassigns the equipment from this facility.'),
    ).toBeTruthy()
    expect(screen.getByText('Projector Set')).toBeTruthy()
  })

  it('cancel never calls the handler and dismisses the dialog', async () => {
    const onConfirm = vi.fn()
    render(<Harness onConfirm={onConfirm} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() =>
      expect(screen.queryByText('Remove resource?')).toBeNull(),
    )
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('confirm runs the handler exactly once and closes on success', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    render(<Harness onConfirm={onConfirm} />)
    fireEvent.click(screen.getByRole('button', { name: 'Remove resource' }))
    await waitFor(() =>
      expect(screen.queryByText('Remove resource?')).toBeNull(),
    )
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('a failing handler keeps the dialog open and shows the error inline', async () => {
    const onConfirm = vi
      .fn()
      .mockRejectedValue(new Error('Unable to remove the resource.'))
    render(<Harness onConfirm={onConfirm} />)
    fireEvent.click(screen.getByRole('button', { name: 'Remove resource' }))
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('Unable to remove the resource.')
    // Context preserved: the dialog is still open for a retry.
    expect(screen.getByText('Remove resource?')).toBeTruthy()
  })

  it('a pending request cannot be submitted twice or dismissed', async () => {
    let resolve!: () => void
    const onConfirm = vi.fn(
      () => new Promise<void>((res) => (resolve = res)),
    )
    render(<Harness onConfirm={onConfirm} />)
    const confirmButton = screen.getByRole('button', { name: 'Remove resource' })
    fireEvent.click(confirmButton)
    // The button is busy loading and the cancel button is disabled while the
    // request is in flight.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Cancel' })).toHaveProperty(
        'disabled',
        true,
      ),
    )
    fireEvent.click(confirmButton)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    resolve()
    await waitFor(() =>
      expect(screen.queryByText('Remove resource?')).toBeNull(),
    )
  })

  it('warning tone renders the primary (non-danger) confirm button', () => {
    render(<Harness onConfirm={vi.fn().mockResolvedValue(undefined)} tone="warning" />)
    // The danger variant carries text-white; the primary (brand) variant is
    // asserted here by the absence of the danger classes.
    const button = screen.getByRole('button', { name: 'Remove resource' })
    expect(button.className).not.toContain('bg-status-rejected')
  })
})
