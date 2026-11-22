import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'
import type { Recommendation, ReservableResource } from '@/lib/types'

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }))
vi.mock('@/hooks/queries', () => ({
  useRecommendResources: () => ({ mutate }),
}))

import { useSuggestedResources, type UseSuggestedResourcesArgs } from './useSuggestedResources'

const equipment: ReservableResource[] = [
  {
    id: 10,
    name: 'Lecture Projector',
    category: { id: 1, name: 'Projectors', icon: '', description: '' },
    description: '',
    total_quantity: 4,
    unit: 'unit',
    status: 'AVAILABLE',
    status_label: 'Available',
    image: null,
    availability: { total: 4, available: 4, reserved: 0, under_maintenance: 0, status: 'AVAILABLE' },
  },
]

const args: UseSuggestedResourcesArgs = {
  active: true,
  eventType: 'WORKSHOP',
  eventName: 'Programming workshop',
  participants: 24,
  equipment,
  facilityId: 3,
  dateISO: '2026-12-10',
  startTime: '09:00',
  endTime: '12:00',
  purpose: 'Build a small application',
  staffNotes: '',
  requesterType: 'CAMPUS',
}

const recommendation: Recommendation = {
  equipment_id: 10,
  name: 'Lecture Projector',
  category: 'Projectors',
  quantity: 1,
  available: 3,
  recommended: 1,
  status: 'AVAILABLE',
  can_fulfill: true,
  reason: 'Recommended because the event details indicate a presentation.',
  calculation: '1 × 1',
  warning: null,
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  mutate.mockReset()
})

describe('useSuggestedResources', () => {
  it('debounces requests and recalculates quantities from the latest participants', async () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ input }) => useSuggestedResources(input), {
      initialProps: { input: args },
    })

    await act(async () => { vi.advanceTimersByTime(350) })
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(mutate.mock.calls[0][0]).toMatchObject({
      event_name: 'Programming workshop',
      facility_id: 3,
      date: '2026-12-10',
      start_time: '09:00',
      end_time: '12:00',
    })

    act(() => mutate.mock.calls[0][1].onSuccess({ recommendations: [recommendation] }))
    expect(result.current.suggestions[0]).toMatchObject({ quantity: 1, recommended: 1 })

    rerender({ input: { ...args, participants: 200 } })
    await act(async () => { vi.advanceTimersByTime(350) })
    expect(mutate.mock.calls[1][0]).toMatchObject({ expected_participants: 200 })

    act(() => mutate.mock.calls[1][1].onSuccess({
      recommendations: [{ ...recommendation, quantity: 2, recommended: 2, available: 2 }],
    }))
    expect(result.current.suggestions[0]).toMatchObject({ quantity: 2, recommended: 2, available: 2 })
  })

  it('keeps a partial-stock recommendation visible with its shortage warning', async () => {
    vi.useFakeTimers()
    const { result } = renderHook(({ input }) => useSuggestedResources(input), {
      initialProps: { input: args },
    })
    await act(async () => { vi.advanceTimersByTime(350) })

    const partial = {
      ...recommendation,
      quantity: 4,
      recommended: 3,
      available: 3,
      status: 'PARTIAL' as const,
      can_fulfill: false,
      warning: 'Only 3 of the recommended 4 units are currently available.',
    }
    act(() => mutate.mock.calls[0][1].onSuccess({ recommendations: [partial, { ...partial, equipment_id: 99 }] }))

    expect(result.current.suggestions).toHaveLength(1)
    expect(result.current.suggestions[0]).toMatchObject({
      equipmentId: 10,
      quantity: 4,
      recommended: 3,
      status: 'PARTIAL',
      warning: partial.warning,
    })
    // The Other equipment list is synchronised from the raw response, so an
    // unavailable recommendation (id 99 is not offered here) still owns its row.
    expect([...result.current.recommendedIds]).toEqual([10])
  })

  it('remembers an ignored suggestion across unrelated edits and resets it with the facility', async () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ input }) => useSuggestedResources(input), {
      initialProps: { input: args },
    })
    await act(async () => { vi.advanceTimersByTime(350) })
    act(() => mutate.mock.calls[0][1].onSuccess({ recommendations: [recommendation] }))

    act(() => result.current.ignore(10))
    expect(result.current.suggestions).toEqual([])
    expect(result.current.recommendedIds.size).toBe(0)

    rerender({ input: { ...args, eventName: 'Programming workshop (updated)' } })
    await act(async () => { vi.advanceTimersByTime(350) })
    act(() => mutate.mock.calls[1][1].onSuccess({ recommendations: [recommendation] }))
    expect(result.current.suggestions).toEqual([])

    rerender({ input: { ...args, facilityId: 4 } })
    await act(async () => { vi.advanceTimersByTime(350) })
    act(() => mutate.mock.calls[2][1].onSuccess({ recommendations: [recommendation] }))
    expect(result.current.suggestions.map((item) => item.equipmentId)).toEqual([10])
  })

  it('asks for missing event details instead of requesting recommendations', async () => {
    vi.useFakeTimers()
    const { result } = renderHook(({ input }) => useSuggestedResources(input), {
      initialProps: { input: { ...args, eventType: '' as const, participants: 0 } },
    })
    await act(async () => { vi.advanceTimersByTime(350) })

    expect(mutate).not.toHaveBeenCalled()
    expect(result.current.missingDetails).toEqual(['event type', 'expected participants'])
    expect(result.current.suggestions).toEqual([])
  })

  it('does not let an old schedule response replace newer recommendations', async () => {
    vi.useFakeTimers()
    const { result, rerender } = renderHook(({ input }) => useSuggestedResources(input), {
      initialProps: { input: args },
    })
    await act(async () => { vi.advanceTimersByTime(350) })
    const oldRequest = mutate.mock.calls[0][1]

    rerender({ input: { ...args, facilityId: 4, dateISO: '2026-12-11' } })
    await act(async () => { vi.advanceTimersByTime(350) })
    const currentRequest = mutate.mock.calls[1][1]
    expect(mutate.mock.calls[1][0]).toMatchObject({ facility_id: 4, date: '2026-12-11' })
    act(() => oldRequest.onSuccess({ recommendations: [] }))
    act(() => currentRequest.onSuccess({ recommendations: [recommendation] }))
    expect(result.current.suggestions.map((item) => item.equipmentId)).toEqual([10])
  })
})
