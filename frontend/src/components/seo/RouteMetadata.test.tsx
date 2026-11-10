import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { RouteMetadataManager } from './RouteMetadata'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <RouteMetadataManager />
    </MemoryRouter>,
  )
}

describe('RouteMetadataManager', () => {
  it('sets public about metadata and an HTTPS canonical URL', async () => {
    renderAt('/about')

    await waitFor(() => {
      expect(document.title).toBe('About SAS RESERVE | NORSU-BSC')
      expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
        'content',
        'index,follow',
      )
      expect(document.querySelector('link[rel="canonical"]')).toHaveAttribute(
        'href',
        'https://sasreserve.pgsytems.asia/about',
      )
      expect(document.querySelector('meta[property="og:title"]')).toHaveAttribute(
        'content',
        'About SAS RESERVE | NORSU-BSC',
      )
    })
  })

  it('marks private route metadata noindex and removes its canonical URL', async () => {
    renderAt('/reservations/123')

    await waitFor(() => {
      expect(document.title).toBe('Reservation Details | SAS RESERVE')
      expect(document.querySelector('meta[name="robots"]')).toHaveAttribute(
        'content',
        'noindex,nofollow',
      )
      expect(document.querySelector('meta[name="googlebot"]')).toHaveAttribute(
        'content',
        'noindex,nofollow',
      )
      expect(document.querySelector('link[rel="canonical"]')).toBeNull()
      expect(document.querySelector('meta[property="og:url"]')).toBeNull()
    })
  })
})
