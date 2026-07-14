import { create } from 'zustand'

interface ScopeState {
  runId: string | null
  datasetId: string | null
  setScope: (runId: string, datasetId: string) => void
}

/** The active run/dataset scope selected in the TopBar, read by every view. */
export const useScopeStore = create<ScopeState>((set) => ({
  runId: null,
  datasetId: null,
  setScope: (runId, datasetId) => set({ runId, datasetId }),
}))
