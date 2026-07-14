import { NavLink, useLocation } from 'react-router-dom'
import { navRoutes } from './routes'
import './NavRail.css'

/** Every tab is a first-class, one-click-away route (Dashboard is the
 * landing view; Findings/Genes/PAS/Cells are normal readable tables; only
 * "Browser" is the IGV-style genome browser) -- these are just visual
 * dividers between groups, matching `navRoutes`'s order in routes.tsx:
 * Dashboard (its own group) | Browser (the one IGV tab) | the readable
 * tables (Findings + entity browsers) | secondary analysis views. */
const GROUP_BREAK_AFTER = new Set(['/', '/browser', '/browse/cells'])

export function NavRail() {
  const location = useLocation()
  return (
    <nav className="nav-rail" aria-label="Primary">
      <ul>
        {navRoutes.map((r) => {
          // `matchPrefix` forces the link active for any deep-linked path
          // under it (e.g. the browser link stays highlighted on
          // "/genes/ENSG..." even though that path isn't itself in
          // navRoutes -- it was reached by row-click/search, not this nav).
          const forcedActive = r.matchPrefix ? location.pathname.startsWith(r.matchPrefix) : false
          return (
            <li key={r.path} className={GROUP_BREAK_AFTER.has(r.path) ? 'nav-rail__group-end' : undefined}>
              <NavLink
                to={r.path}
                className={({ isActive }) => (isActive || forcedActive ? 'nav-rail__link nav-rail__link--active' : 'nav-rail__link')}
                end={r.path === '/'}
              >
                {r.label}
              </NavLink>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
