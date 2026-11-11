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
  selectedItems: {},
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
  it('debounces context, filters selected equipment, and rejects partial inventory', async () => {
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

    const partialInventory = { ...recommendation, quantity: 4, recommended: 3, available: 3, status: 'PARTIAL' as const }
    act(() => mutate.mock.calls[0][1].onSuccess({ recommendations: [recommendation, partialInventory] }))
    expect(result.current.suggestions.map((item) => item.equipmentId)).toEqual([10])

    rerender({ input: { ...args, selectedItems: { 10: 1 } } })
    expect(result.current.suggestions).toEqual([])
    rerender({ input: args })
    expect(result.current.suggestions.map((item) => item.name)).toEqual(['Lecture Projector'])
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
