import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { PinnedEntity } from '@lib/contract/types'

interface PinState {
  pinned: PinnedEntity[]
  pin: (entity: Omit<PinnedEntity, 'pinnedAt'>) => void
  unpin: (kind: PinnedEntity['kind'], id: string) => void
  clear: () => void
  isPinned: (kind: PinnedEntity['kind'], id: string) => boolean
}

/** Pinned entities for the PinTray / Compare view. Persisted to localStorage. */
export const usePinStore = create<PinState>()(
  persist(
    (set, get) => ({
      pinned: [],
      pin: (entity) =>
        set((state) => {
          if (state.pinned.some((p) => p.kind === entity.kind && p.id === entity.id)) {
            return state
          }
          return { pinned: [...state.pinned, { ...entity, pinnedAt: Date.now() }] }
        }),
      unpin: (kind, id) =>
        set((state) => ({
          pinned: state.pinned.filter((p) => !(p.kind === kind && p.id === id)),
        })),
      clear: () => set({ pinned: [] }),
      isPinned: (kind, id) => get().pinned.some((p) => p.kind === kind && p.id === id),
    }),
    { name: 'peakatail-hub-pins' },
  ),
)
