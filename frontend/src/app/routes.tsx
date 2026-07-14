import type { ReactNode } from 'react'
import { FindingsView } from '@views/findings/FindingsView'
import { GeneView } from '@views/gene/GeneView'
import { GeneBrowser } from '@views/browse/GeneBrowser'
import { PasBrowser } from '@views/browse/PasBrowser'
import { CellBrowser } from '@views/browse/CellBrowser'
import { DashboardView } from '@views/dashboard/DashboardView'
import { UmapView } from '@views/umap/UmapView'
import { QcView } from '@views/qc/QcView'
import { AuditView } from '@views/audit/AuditView'
import { CompareView } from '@views/compare/CompareView'

export interface NavRoute {
  path: string
  label: string
  element: ReactNode
  /** Forces the NavRail link active for any pathname under this prefix
   * (e.g. the genome browser stays highlighted on both "/" and a deep-linked
   * "/genes/ENSG..."). */
  matchPrefix?: string
  /** Omit this route from the NavRail entirely (still reachable by direct
   * navigation/deep link) -- used for the gene-detail path, which duplicates
   * "/"'s browser and is reached by row-click/search, never a nav link. */
  hideFromNav?: boolean
}

// The IGV-style reframe: the genome browser (GeneView) is the landing/
// central surface, reachable at both "/" (no locus yet -- GeneView's own
// empty state prompts a search) and "/genes/:geneId" (a resolved locus).
// Findings/tables are secondary -- FindingsView is no longer a route at
// all, it's mounted in the FindingsDrawer (see AppShell.tsx) toggled from
// the TopBar, never the landing view. Browse (Genes/PAS/Cells) are the
// searchable entity lists that jump the browser. Dashboard (dashboard-team,
// views/dashboard/**) is the "which run/source" surface -- reachable from
// the nav rail, but deliberately NOT "/": the browser stays the one screen
// this app always opens on (RunCard's own click-through already lands on
// `/browse/genes`, not `/dashboard`, once a run is picked).
export const routes: NavRoute[] = [
  { path: '/', label: 'Browser', element: <GeneView />, matchPrefix: '/genes' },
  { path: '/genes/:geneId', label: 'Browser', element: <GeneView />, hideFromNav: true },
  { path: '/dashboard', label: 'Dashboard', element: <DashboardView /> },
  { path: '/browse/genes', label: 'Genes', element: <GeneBrowser /> },
  { path: '/browse/pas', label: 'PAS', element: <PasBrowser /> },
  { path: '/browse/cells', label: 'Cells', element: <CellBrowser /> },
  { path: '/umap', label: 'UMAP', element: <UmapView /> },
  { path: '/qc', label: 'Run / QC', element: <QcView /> },
  { path: '/audit', label: 'Audit', element: <AuditView /> },
  { path: '/compare', label: 'Compare', element: <CompareView /> },
]

/** Routes shown in the left nav rail. */
export const navRoutes: NavRoute[] = routes.filter((r) => !r.hideFromNav)

// FindingsView is deliberately NOT in `routes`/`navRoutes` -- it's mounted
// directly by AppShell inside FindingsDrawer, a secondary slide-over panel
// rather than a page you navigate to. Exported here so AppShell/TopBar
// don't need their own import of a view that belongs to views/findings/**.
export { FindingsView }
