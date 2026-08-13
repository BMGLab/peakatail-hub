import type { ReactNode } from 'react'
import './PageHeader.css'

/**
 * Shared page header used by every view: a title, a short (1-3 sentence)
 * explanation of what the view shows and how to read it, and an optional
 * right-aligned actions/status slot (e.g. UMAP's color-by control, Findings'
 * result count). Keeping this in one place is what makes ten very different
 * views (a table, a track browser, a funnel chart, a comparison grid) read
 * as one product instead of ten scaffolds.
 */
export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: ReactNode
  description: ReactNode
  actions?: ReactNode
  /** Small label above the title, e.g. a mono gene id or run id. */
  eyebrow?: ReactNode
}) {
  return (
    <header className="page-header">
      <div className="page-header__text">
        {eyebrow && <div className="page-header__eyebrow">{eyebrow}</div>}
        <h2 className="page-header__title">{title}</h2>
        <p className="page-header__description">{description}</p>
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  )
}
