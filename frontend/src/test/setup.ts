import '@testing-library/jest-dom/vitest'

// jsdom has no ResizeObserver; @tanstack/react-virtual (used by FindingsView)
// needs one to measure the scroll container. Minimal no-op polyfill so
// virtualized-table tests don't throw.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

if (typeof globalThis.ResizeObserver === 'undefined') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(globalThis as any).ResizeObserver = ResizeObserverStub
}

// jsdom has no layout engine, so `offsetWidth`/`offsetHeight` are always 0.
// @tanstack/react-virtual's `observeElementRect` calls
// `{width: el.offsetWidth, height: el.offsetHeight}` SYNCHRONOUSLY on setup
// (before the ResizeObserver above ever gets a chance to fire), so every
// virtualized container measures as zero-size in tests regardless of the
// `initialRect` option passed to `useVirtualizer` -- `initialRect` is only
// consulted if that synchronous call never happens at all. Without this,
// FindingsView's virtualizer computes a permanently-empty visible range and
// `.findings-view__table tbody` never renders a single <tr> in jsdom, even
// though `rows.length` (and thus `getTotalSize()`) is correct -- exactly
// the real bug this stubs around, just for a different reason than the one
// that hit production (see FindingsView.tsx's `virtualItems` comment).
Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 600 })
Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, value: 800 })

// jsdom implements neither URL.createObjectURL/revokeObjectURL nor
// <canvas> 2D/WebGL contexts. plotly.js runs browser feature-detection at
// *import* time (not just render time), so every test file that pulls in a
// view importing PlotlyChart needs these stubbed or the import itself throws.
if (typeof window.URL.createObjectURL === 'undefined') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window.URL as any).createObjectURL = () => 'blob:mock'
}
if (typeof window.URL.revokeObjectURL === 'undefined') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window.URL as any).revokeObjectURL = () => {}
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
;(HTMLCanvasElement.prototype.getContext as any) = () => null

