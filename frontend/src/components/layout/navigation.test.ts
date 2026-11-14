import { describe, expect, it } from 'vitest'
import { FilePenLine } from 'lucide-react'
import { adminNavigation } from './navigation'

describe('adminNavigation', () => {
  it('includes the dedicated approval letter editor route with a document editing icon', () => {
    expect(adminNavigation).toContainEqual({
      to: '/admin/approval-letter',
      label: 'Approval Letter Management',
      icon: FilePenLine,
    })
  })
})
