import { Route, Routes } from 'react-router-dom'
import { TopBar } from './TopBar'
import { NavRail } from './NavRail'
import { DetailPanel } from './DetailPanel'
import { PinTray } from './PinTray'
import { routes } from './routes'
import './AppShell.css'

export function AppShell() {
  return (
    <div className="app-shell">
      <TopBar />
      <PinTray />
      <div className="app-shell__body">
        <NavRail />
        <main className="app-shell__main">
          <Routes>
            {routes.map((r) => (
              <Route key={r.path} path={r.path} element={r.element} />
            ))}
          </Routes>
        </main>
        <DetailPanel />
      </div>
    </div>
  )
}
