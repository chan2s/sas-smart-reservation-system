import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * A manifest that points at a missing, corrupt, or mis-sized icon fails
 * installability, and browsers are not always explicit about why. These checks
 * read the real files shipped in `public/`.
 */

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])

function readPng(file: string) {
  // Vitest runs from the frontend package root, where `public/` is served from.
  const filePath = path.resolve(process.cwd(), 'public', file)
  const buffer = readFileSync(filePath)
  const isPng = buffer.subarray(0, 8).equals(PNG_SIGNATURE)
  const chunkType = buffer.subarray(12, 16).toString('ascii')
  return {
    isPng,
    chunkType,
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
    bytes: buffer.byteLength,
  }
}

describe('PWA icons', () => {
  it.each([
    ['pwa-192x192.png', 192],
    ['pwa-512x512.png', 512],
    ['pwa-maskable-512x512.png', 512],
    ['apple-touch-icon.png', 180],
  ])('%s is a %ipx PNG', (file, size) => {
    const png = readPng(file as string)
    expect(png.isPng).toBe(true)
    expect(png.chunkType).toBe('IHDR')
    expect(png.width).toBe(size)
    expect(png.height).toBe(size)
    // Not a 1x1 placeholder or a truncated file.
    expect(png.bytes).toBeGreaterThan(500)
  })
})
