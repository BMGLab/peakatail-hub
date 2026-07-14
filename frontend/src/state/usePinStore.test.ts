import { afterEach, describe, expect, it } from 'vitest'
import { usePinStore } from './usePinStore'

afterEach(() => {
  usePinStore.getState().clear()
})

describe('usePinStore', () => {
  it('pins an entity and reports it as pinned', () => {
    usePinStore.getState().pin({ kind: 'gene', id: 'ENSG1', label: 'TP53' })

    const state = usePinStore.getState()
    expect(state.pinned).toHaveLength(1)
    expect(state.pinned[0]).toMatchObject({ kind: 'gene', id: 'ENSG1', label: 'TP53' })
    expect(state.isPinned('gene', 'ENSG1')).toBe(true)
  })

  it('does not duplicate an already-pinned entity', () => {
    usePinStore.getState().pin({ kind: 'gene', id: 'ENSG1', label: 'TP53' })
    usePinStore.getState().pin({ kind: 'gene', id: 'ENSG1', label: 'TP53' })

    expect(usePinStore.getState().pinned).toHaveLength(1)
  })

  it('unpins an entity', () => {
    usePinStore.getState().pin({ kind: 'pas', id: 'chr1:100:+', label: 'chr1:100:+' })
    usePinStore.getState().unpin('pas', 'chr1:100:+')

    expect(usePinStore.getState().pinned).toHaveLength(0)
    expect(usePinStore.getState().isPinned('pas', 'chr1:100:+')).toBe(false)
  })
})
