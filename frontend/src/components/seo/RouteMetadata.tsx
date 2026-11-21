import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

const SITE_ORIGIN = 'https://sasreserve.pgsytems.asia'
const SITE_TITLE = 'GSO RESERVE | NORSU-BSC Facility and Resource Reservation System'
const SITE_DESCRIPTION =
  'GSO RESERVE is a web-based facility and resource reservation system for Negros Oriental State University – Bayawan-Sta. Catalina Campus (NORSU-BSC), designed to streamline facility reservations and resource management.'
const SOCIAL_IMAGE = `${SITE_ORIGIN}/pwa-512x512.png`

type RouteMetadata = {
  title: string
  description: string
  keywords?: string
  indexable: boolean
}

const indexedRoutes: Record<string, RouteMetadata> = {
  '/': {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    keywords:
      'NORSU-BSC, campus facility reservations, university resource management, Bayawan-Sta. Catalina Campus',
    indexable: true,
  },
  '/about': {
    title: 'About GSO RESERVE | NORSU-BSC',
    description:
      'Learn how GSO RESERVE helps organizations explore campus facilities, submit reservation requests, and manage event resources at NORSU-BSC.',
    keywords:
      'about GSO RESERVE, NORSU-BSC, campus facilities, event resource management',
    indexable: true,
  },
}

const privateRouteTitles: Array<[RegExp, string]> = [
  [/^\/reserve$/, 'Choose a Reservation Type | GSO RESERVE'],
  [/^\/reserve\/internal$/, 'Internal Reservation Request | GSO RESERVE'],
  [/^\/reserve\/external$/, 'External Reservation Request | GSO RESERVE'],
  [/^\/track-reservation$/, 'Track a Reservation | GSO RESERVE'],
  [/^\/login$/, 'Sign In | GSO RESERVE'],
  [/^\/register$/, 'Register | GSO RESERVE'],
  [/^\/auth\/callback$/, 'Completing Sign In | GSO RESERVE'],
  [/^\/dashboard$/, 'Dashboard | GSO RESERVE'],
  [/^\/offline$/, 'Offline Reservations | GSO RESERVE'],
  [/^\/onboarding\/affiliation$/, 'Organization Affiliation | GSO RESERVE'],
  [/^\/facilities$/, 'Facilities | GSO RESERVE'],
  [/^\/facilities\/[^/]+$/, 'Facility Details | GSO RESERVE'],
  [/^\/facilities\/[^/]+\/resources$/, 'Facility Resources | GSO RESERVE'],
  [/^\/reservations$/, 'Reservations | GSO RESERVE'],
  [/^\/reservations\/new$/, 'Create a Reservation | GSO RESERVE'],
  [/^\/reservations\/[^/]+\/edit$/, 'Edit Reservation | GSO RESERVE'],
  [/^\/reservations\/[^/]+\/check-in$/, 'Reservation Check-In | GSO RESERVE'],
  [/^\/reservations\/[^/]+\/check-out$/, 'Reservation Check-Out | GSO RESERVE'],
  [/^\/reservations\/[^/]+$/, 'Reservation Details | GSO RESERVE'],
  [/^\/calendar$/, 'Reservation Calendar | GSO RESERVE'],
  [/^\/equipment$/, 'Equipment | GSO RESERVE'],
  [/^\/equipment\/[^/]+$/, 'Equipment Details | GSO RESERVE'],
  [/^\/analytics$/, 'Analytics | GSO RESERVE'],
  [/^\/reports$/, 'Reports | GSO RESERVE'],
  [/^\/notifications$/, 'Notifications | GSO RESERVE'],
  [/^\/settings$/, 'Account Settings | GSO RESERVE'],
  [/^\/help$/, 'Help | GSO RESERVE'],
  [/^\/audit-log$/, 'Audit Log | GSO RESERVE'],
  [/^\/organizations$/, 'Organizations | GSO RESERVE'],
  [/^\/admin\/users$/, 'User Administration | GSO RESERVE'],
  [/^\/admin\/approval-letter$/, 'Approval Letter Management | GSO RESERVE'],
  [/^\/admin\/login-activity$/, 'Login Activity | GSO RESERVE'],
]

function routeMetadata(pathname: string): RouteMetadata {
  const indexed = indexedRoutes[pathname]
  if (indexed) return indexed

  const route = privateRouteTitles.find(([pattern]) => pattern.test(pathname))
  return {
    title: route?.[1] ?? 'Page Not Found | GSO RESERVE',
    description: 'GSO RESERVE application page.',
    indexable: false,
  }
}

function setMeta(attribute: 'name' | 'property', key: string, content: string | null) {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[${attribute}="${key}"]`)
  if (!content) {
    element?.remove()
    return
  }
  if (!element) {
    element = document.createElement('meta')
    element.setAttribute(attribute, key)
    document.head.appendChild(element)
  }
  element.content = content
}

function setCanonical(pathname: string | null) {
  let element = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!pathname) {
    element?.remove()
    return
  }
  if (!element) {
    element = document.createElement('link')
    element.rel = 'canonical'
    document.head.appendChild(element)
  }
  element.href = `${SITE_ORIGIN}${pathname === '/' ? '/' : pathname}`
}

/** Updates client-side route metadata while keeping application routes noindex by default. */
export function RouteMetadataManager() {
  const { pathname } = useLocation()

  useEffect(() => {
    const metadata = routeMetadata(pathname)
    const canonicalPath = metadata.indexable ? pathname : null
    const pageUrl = canonicalPath ? `${SITE_ORIGIN}${canonicalPath}` : null
    const robots = metadata.indexable ? 'index,follow' : 'noindex,nofollow'

    document.documentElement.lang = 'en'
    document.title = metadata.title
    setMeta('name', 'description', metadata.description)
    setMeta('name', 'keywords', metadata.keywords ?? null)
    setMeta('name', 'robots', robots)
    setMeta('name', 'googlebot', robots)
    setMeta('property', 'og:type', 'website')
    setMeta('property', 'og:site_name', 'GSO RESERVE')
    setMeta('property', 'og:locale', 'en_US')
    setMeta('property', 'og:title', metadata.title)
    setMeta('property', 'og:description', metadata.description)
    setMeta('property', 'og:url', pageUrl)
    setMeta('property', 'og:image', SOCIAL_IMAGE)
    setMeta('name', 'twitter:card', 'summary_large_image')
    setMeta('name', 'twitter:title', metadata.title)
    setMeta('name', 'twitter:description', metadata.description)
    setMeta('name', 'twitter:image', SOCIAL_IMAGE)
    setCanonical(canonicalPath)
  }, [pathname])

  return null
}
