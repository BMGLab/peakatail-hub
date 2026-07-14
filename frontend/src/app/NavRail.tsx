import { NavLink } from 'react-router-dom'
import { navRoutes } from './routes'
import './NavRail.css'

export function NavRail() {
  return (
    <nav className="nav-rail" aria-label="Primary">
      <ul>
        {navRoutes.map((r) => (
          <li key={r.path}>
            <NavLink to={r.path} className={({ isActive }) => (isActive ? 'nav-rail__link nav-rail__link--active' : 'nav-rail__link')} end={r.path === '/'}>
              {r.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
