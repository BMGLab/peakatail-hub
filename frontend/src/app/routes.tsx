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
import { ResultsView } from '@views/results/ResultsView'
import { ResultsCelltypeView } from '@views/results/ResultsCelltypeView'

export interface NavRoute {
  path: string
  label: string
  element: ReactNode
  /** Forces the NavRail link active for any pathname under this prefix
   * (e.g. the "Browser" link stays highlighted on both "/browser" and a
   * deep-linked "/genes/ENSG..."). */
  matchPrefix?: string
  /** Omit this route from the NavRail entirely (still reachable by direct
   * navigation/deep link) -- used for the gene-detail path, which duplicates
   * "/browser" and is reached by row-click/search, never a nav link. */
  hideFromNav?: boolean
}

// Route layout (per main's arbitration of the dashboard/browser landing-view
// conflict, superseding the earlier "browser owns /" reframe): Dashboard is
// the true landing view at "/" -- it's where a user with zero sources
// registered starts, and where run/source selection happens. The IGV-style
// genome browser (GeneView) is its OWN tab at "/browser" (plus the
// "/genes/:geneId" deep-link, reached by row-click/search, not a nav link).
//
// Tables stay FIRST-CLASS, not secondary: Findings is a normal full route
// again (moved OFF "/" but never demoted into a drawer -- see AppShell.tsx),
// same as the Genes/PAS/Cells browsers. Only the geneview tab is IGV-style;
// everything else is a normal, readable table view. The TopBar's location
// bar still jumps straight to "/genes/:geneId" from anywhere in the app.
export const routes: NavRoute[] = [
  { path: '/', label: 'Dashboard', element: <DashboardView /> },
  // Primary nav (per explicit product direction, 2026-08-14): "cell types ->
  // stages -> genes" matters more than flat gene browsing -- the professor's
  // headline finding (3'UTR shortening/lengthening across disease stages) is
  // organized by cell type first. Placed right after Dashboard, ahead of the
  // gene Browser.
  { path: '/results', label: 'Cell Types', element: <ResultsView />, matchPrefix: '/results' },
  { path: '/results/:celltype', label: 'Cell Types', element: <ResultsCelltypeView />, hideFromNav: true },
  { path: '/browser', label: 'Browser', element: <GeneView />, matchPrefix: '/genes' },
  { path: '/genes/:geneId', label: 'Browser', element: <GeneView />, hideFromNav: true },
  { path: '/findings', label: 'Findings', element: <FindingsView /> },
  { path: '/browse/genes', label: 'Genes', element: <GeneBrowser /> },
  { path: '/browse/pas', label: 'PAS', element: <PasBrowser /> },
  { path: '/browse/cells', label: 'Cells', element: <CellBrowser /> },
  { path: '/umap', label: 'UMAP', element: <UmapView /> },
  { path: '/qc', label: 'Run / QC', element: <QcView /> },
  { path: '/audit', label: 'Audit', element: <AuditView /> },
  { path: '/compare', label: 'Compare', element: <CompareView /> },
]

/** Routes shown in the left nav rail -- every tab, one click apart. */
export const navRoutes: NavRoute[] = routes.filter((r) => !r.hideFromNav)
