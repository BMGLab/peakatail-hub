// Human-readable labels for the length-trend-across-stages `direction`
// field (SwitchTrend.direction / SwitchTrendGeneRow.direction -- the
// professor's headline finding: whether a gene's/celltype's 3'UTR gets
// shorter or longer across disease stages). "decreasing"/"increasing" is
// the raw statistical direction of the PDUI-vs-stage slope, not obvious to
// a biologist reading the UI -- 2026-08-14 fix: label it as the biological
// meaning instead. NOT the same as FindingRow.direction (fisher/nb_pairwise
// switch-diff calls), which is already worded "shorten"/"lengthen" and
// needs no mapping.
export function trendDirectionLabel(direction: string | null | undefined): string {
  switch (direction) {
    case 'decreasing':
      return "3′UTR shortening"
    case 'increasing':
      return "3′UTR lengthening"
    default:
      return direction ?? '—'
  }
}
