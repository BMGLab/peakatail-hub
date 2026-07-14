import type { ReactNode } from 'react'
import { FindingsView } from '@views/findings/FindingsView'
import { GeneView } from '@views/gene/GeneView'
import { UmapView } from '@views/umap/UmapView'
import { QcView } from '@views/qc/QcView'
import { AuditView } from '@views/audit/AuditView'
import { CompareView } from '@views/compare/CompareView'

export interface NavRoute {
  path: string
  label: string
  element: ReactNode
  /** Matches gene detail path prefix so NavRail can highlight it from a deep link. */
  matchPrefix?: string
}

export const routes: NavRoute[] = [
  { path: '/', label: 'Findings', element: <FindingsView /> },
  { path: '/genes/:geneId', label: 'Gene', element: <GeneView />, matchPrefix: '/genes' },
  { path: '/umap', label: 'UMAP', element: <UmapView /> },
  { path: '/qc', label: 'Run / QC', element: <QcView /> },
  { path: '/audit', label: 'Audit', element: <AuditView /> },
  { path: '/compare', label: 'Compare', element: <CompareView /> },
]

/** Routes shown in the left nav rail (gene detail is reached via row-click, not nav). */
export const navRoutes = routes.filter((r) => r.path !== '/genes/:geneId')
