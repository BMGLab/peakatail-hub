import { useNavigate } from 'react-router-dom'
import { usePinStore } from '@state/usePinStore'
import './PinTray.css'

/** Shows currently pinned entities; supports un-pinning and jumping to Compare. */
export function PinTray() {
  const pinned = usePinStore((s) => s.pinned)
  const unpin = usePinStore((s) => s.unpin)
  const navigate = useNavigate()

  if (pinned.length === 0) {
    return (
      <div className="pin-tray pin-tray--empty">
        <span className="state-message">No pinned entities yet. Pin a gene / PAS / cell from the detail panel.</span>
      </div>
    )
  }

  return (
    <div className="pin-tray">
      <ul className="pin-tray__list">
        {pinned.map((p) => (
          <li key={`${p.kind}-${p.id}`} className="pin-tray__item">
            <span className="badge badge--neutral">{p.kind}</span>
            <span className="pin-tray__label">{p.label}</span>
            <button type="button" aria-label={`Unpin ${p.label}`} onClick={() => unpin(p.kind, p.id)}>
              ×
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="pin-tray__compare" onClick={() => navigate('/compare')}>
        Compare ({pinned.length})
      </button>
    </div>
  )
}
