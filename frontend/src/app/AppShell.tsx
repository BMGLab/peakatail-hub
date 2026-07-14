import { Route, Routes } from 'react-router-dom'
import { TopBar } from './TopBar'
import { NavRail } from './NavRail'
import { DetailPanel } from './DetailPanel'
import { PinTray } from './PinTray'
import { FindingsDrawer } from './FindingsDrawer'
import { routes } from './routes'
import './AppShell.css'

// IGV-style reframe: the genome browser (GeneView, mounted at "/") is the
// central surface -- `<main>` holds it directly, full-bleed, with no
// findings/table competing for that space. Findings is a secondary
// slide-over (<FindingsDrawer>, toggled from the TopBar), not a route.
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
      <FindingsDrawer />
    </div>
  )
}
