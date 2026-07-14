import { create } from 'zustand'

interface DrawerState {
  /** The Findings table is a secondary supporting panel (IGV-style reframe:
   * the genome browser is the landing/central surface, not a spreadsheet) --
   * this tracks whether its slide-over drawer is open. Extend with more
   * named drawers here if another secondary panel needs one later. */
  findingsOpen: boolean
  openFindings: () => void
  closeFindings: () => void
  toggleFindings: () => void
}

export const useDrawerStore = create<DrawerState>((set) => ({
  findingsOpen: false,
  openFindings: () => set({ findingsOpen: true }),
  closeFindings: () => set({ findingsOpen: false }),
  toggleFindings: () => set((s) => ({ findingsOpen: !s.findingsOpen })),
}))
