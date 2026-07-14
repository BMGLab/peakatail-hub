import { create } from 'zustand'
import type { SelectedEntity } from '@lib/contract/types'

interface SelectionState {
  selected: SelectedEntity | null
  select: (entity: SelectedEntity) => void
  clear: () => void
}

/** Currently selected entity for the shared right-hand DetailPanel. */
export const useSelectionStore = create<SelectionState>((set) => ({
  selected: null,
  select: (entity) => set({ selected: entity }),
  clear: () => set({ selected: null }),
}))
