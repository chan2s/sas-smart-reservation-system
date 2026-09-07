import { Badge } from '@/components/ui/Badge'
import type { Equipment, EquipmentCondition } from '@/lib/types'

export function EquipmentStatusBadge({
  item,
}: {
  item: Pick<Equipment, 'is_active' | 'status' | 'availability'>
}) {
  if (!item.is_active) return <Badge tone="gray">Archived</Badge>
  switch (item.status) {
    case 'AVAILABLE':
      return item.availability.status === 'PARTIAL' ? (
        <Badge tone="sky">In use</Badge>
      ) : item.availability.status === 'UNAVAILABLE' ? (
        <Badge tone="rose">Unavailable</Badge>
      ) : (
        <Badge tone="emerald">Available</Badge>
      )
    case 'MAINTENANCE':
      return <Badge tone="orange">Under maintenance</Badge>
    case 'UNAVAILABLE':
      return <Badge tone="rose">Unavailable</Badge>
    case 'RETIRED':
      return <Badge tone="gray">Retired</Badge>
  }
}

export function ConditionBadge({ condition }: { condition: EquipmentCondition }) {
  if (condition === 'EXCELLENT' || condition === 'GOOD')
    return <Badge tone="emerald">{condition === 'EXCELLENT' ? 'Excellent' : 'Good'}</Badge>
  if (condition === 'FAIR') return <Badge tone="amber">Fair</Badge>
  return <Badge tone="rose">{condition === 'POOR' ? 'Poor' : 'Damaged'}</Badge>
}