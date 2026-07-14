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

