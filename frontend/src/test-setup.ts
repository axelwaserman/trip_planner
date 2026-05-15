import '@testing-library/jest-dom'

// jsdom 29 + vitest 4 do not ship a working localStorage by default — install a
// minimal in-memory shim so tests get a consistent Storage API across the suite.
const storageShim = (() => {
  let store: Record<string, string> = {}
  return {
    getItem(key: string): string | null {
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null
    },
    setItem(key: string, value: string): void {
      store[key] = String(value)
    },
    removeItem(key: string): void {
      delete store[key]
    },
    clear(): void {
      store = {}
    },
    key(index: number): string | null {
      return Object.keys(store)[index] ?? null
    },
    get length(): number {
      return Object.keys(store).length
    },
  }
})()

Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  writable: true,
  value: storageShim,
})
Object.defineProperty(globalThis, 'sessionStorage', {
  configurable: true,
  writable: true,
  value: storageShim,
})
