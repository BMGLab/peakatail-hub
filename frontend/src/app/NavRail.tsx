import { NavLink, useLocation } from 'react-router-dom'
import { navRoutes } from './routes'
import './NavRail.css'

/** Genome-browser-first grouping: the browser link leads (its own group),
 * then "which run/data" (Dashboard) + the searchable entity browsers, then
 * everything else -- matches how `navRoutes` is ordered in routes.tsx, this
 * just draws a divider after each group so the IGV-style hierarchy
 * (browser > data > secondary analysis views) reads visually, not just in
 * list order. */
const GROUP_BREAK_AFTER = new Set(['/', '/browse/cells'])

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
