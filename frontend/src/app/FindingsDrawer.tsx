import { useEffect } from 'react'
import { FindingsView } from '@views/findings/FindingsView'
import { useDrawerStore } from '@state/useDrawerStore'
import './FindingsDrawer.css'

/**
 * Findings as a secondary slide-over panel, not the landing view -- the
 * IGV-style reframe makes the genome browser (GeneView, at "/") the
 * central surface; this drawer is how the findings table stays reachable
 * without competing for that role. Toggled from the TopBar's "Findings"
 * button (see TopBar.tsx) or Escape-to-close while open.
 */
export function FindingsDrawer() {
  const open = useDrawerStore((s) => s.findingsOpen)
  const close = useDrawerStore((s) => s.closeFindings)

  useEffect(() => {
    if (!open) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, close])

  if (!open) return null

  return (
    <div className="findings-drawer" role="dialog" aria-label="Findings" aria-modal="false">
      <div className="findings-drawer__backdrop" onClick={close} />
      <div className="findings-drawer__panel">
        <div className="findings-drawer__header">
          <h3>Findings</h3>
          <button type="button" className="findings-drawer__close" onClick={close} aria-label="Close findings drawer">
            ×
          </button>
        </div>
        <div className="findings-drawer__body">
          <FindingsView />
        </div>
      </div>
    </div>
  )
}
