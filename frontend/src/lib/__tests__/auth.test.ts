/**
 * Tests for the auth helper module — Plan 03 creates `frontend/src/lib/auth.ts`
 * exporting getToken / setToken / clearToken / apiFetch.
 *
 * Behavior contracts (per CONTEXT.md D-01, D-02, D-04):
 *   - JWT lives in localStorage under key 'auth_token'
 *   - apiFetch injects `Authorization: Bearer <token>` on every /api/* call
 *   - On 401: clearToken(), redirect to /login?flash=session_expired&from=<path>,
 *     throw Error('Session expired') so caller's .catch() runs
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch, clearToken, getToken, setToken } from '../auth'

describe('auth helper module', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('getToken returns null when localStorage is empty', () => {
    // Arrange: localStorage is cleared in beforeEach.
    // Act
    const token = getToken()
    // Assert
    expect(token).toBeNull()
  })

  it('setToken stores the value under key auth_token', () => {
    // Act
    setToken('jwt.abc')
    // Assert
    expect(localStorage.getItem('auth_token')).toBe('jwt.abc')
  })

  it('clearToken removes auth_token from localStorage', () => {
    // Arrange
    localStorage.setItem('auth_token', 'jwt.abc')
    // Act
    clearToken()
    // Assert
    expect(localStorage.getItem('auth_token')).toBeNull()
  })

  it('apiFetch injects Authorization: Bearer header when token is present', async () => {
    // Arrange
    setToken('jwt.abc')
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 200 })
    )
    vi.stubGlobal('fetch', fetchMock)

    // Act
    await apiFetch('/api/providers')

    // Assert
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [, init] = fetchMock.mock.calls[0]
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBe('Bearer jwt.abc')
  })

  it('apiFetch does not add Authorization header when token is absent', async () => {
    // Arrange
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 200 })
    )
    vi.stubGlobal('fetch', fetchMock)

    // Act
    await apiFetch('/api/providers')

    // Assert
    const [, init] = fetchMock.mock.calls[0]
    const headers = new Headers(init.headers)
    expect(headers.has('Authorization')).toBe(false)
  })

  it('apiFetch calls clearToken and redirects to /login?flash=session_expired when response is 401', async () => {
    // Arrange
    setToken('jwt.abc')
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 401 })
    )
    vi.stubGlobal('fetch', fetchMock)
    const assignMock = vi.fn()
    // window.location is read-only in jsdom; replace via defineProperty.
    const originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: {
        ...originalLocation,
        pathname: '/',
        search: '',
        assign: assignMock,
      },
    })

    // Act + Assert: throws 'Session expired'
    await expect(apiFetch('/api/providers')).rejects.toThrow('Session expired')

    // Assert: token cleared and redirect issued
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(assignMock).toHaveBeenCalledTimes(1)
    expect(assignMock.mock.calls[0][0]).toContain('/login?flash=session_expired')

    // Restore
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    })
  })

  it('apiFetch preserves the original path in ?from= when redirecting to /login on 401', async () => {
    // Arrange
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 401 })
    )
    vi.stubGlobal('fetch', fetchMock)
    const assignMock = vi.fn()
    const originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: {
        ...originalLocation,
        pathname: '/chat',
        search: '?session=42',
        assign: assignMock,
      },
    })

    // Act
    await expect(apiFetch('/api/providers')).rejects.toThrow('Session expired')

    // Assert
    const target = assignMock.mock.calls[0][0] as string
    expect(target).toContain('from=')
    const fromValue = new URL(target, 'http://localhost').searchParams.get('from')
    expect(fromValue).toBe('/chat?session=42')

    // Restore
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    })
  })
})
