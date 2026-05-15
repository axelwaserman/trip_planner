/**
 * Auth helper module — single source of truth for the JWT auth_token plus the
 * `apiFetch` wrapper that every /api/* call must go through.
 *
 * Per Phase 4.2 CONTEXT.md:
 *   - D-01 — JWT lives in localStorage under key 'auth_token'
 *   - D-02 — On 401: clearToken + redirect to /login?flash=session_expired
 *   - D-04 — Token sent as `Authorization: Bearer <jwt>` on every /api/* call
 *
 * Why a window-level redirect (not useNavigate): this wrapper is called from
 * non-component contexts (useChat effects, ProviderSelector mount, the boot-time
 * /api/auth/me check). React hooks only run inside components, so we use
 * `window.location.assign` and force a full reload — which has the additional
 * useful side effect of resetting any in-flight chat session state.
 */

const TOKEN_KEY = 'auth_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export interface ApiFetchOptions extends Omit<RequestInit, 'headers'> {
  headers?: HeadersInit
}

export async function apiFetch(
  input: string,
  init: ApiFetchOptions = {}
): Promise<Response> {
  const token = getToken()
  const headers = new Headers(init.headers)
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(input, { ...init, headers })

  if (response.status === 401) {
    clearToken()
    const fromPath = window.location.pathname + window.location.search
    const target = `/login?flash=session_expired&from=${encodeURIComponent(fromPath)}`
    window.location.assign(target)
    throw new Error('Session expired')
  }

  return response
}
