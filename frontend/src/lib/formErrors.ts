import { ApiError } from './api'

/**
 * Splits a DRF 400 body into per-field messages and everything else.
 *
 * ``renderedFields`` names the keys the caller displays beside an input. Any
 * other key (``detail``, ``non_field_errors``, an unknown field) is returned in
 * ``general`` so no backend message is silently swallowed.
 */
export function readFieldErrors(
  error: unknown,
  renderedFields: ReadonlySet<string>,
): {
  fields: Record<string, string>
  general: string
} {
  if (
    !(error instanceof ApiError) ||
    !error.data ||
    typeof error.data !== 'object' ||
    Array.isArray(error.data)
  ) {
    return { fields: {}, general: '' }
  }

  const fields: Record<string, string> = {}
  const general: string[] = []

  for (const [key, value] of Object.entries(error.data as Record<string, unknown>)) {
    const message =
      typeof value === 'string'
        ? value.trim()
        : Array.isArray(value)
          ? value.filter((item): item is string => typeof item === 'string').join(' ')
          : ''
    if (!message) continue
    if (renderedFields.has(key)) fields[key] = message
    else general.push(message)
  }

  return { fields, general: general.join(' ') }
}
