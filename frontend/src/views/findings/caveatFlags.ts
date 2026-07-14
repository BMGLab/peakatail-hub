import type { FindingRow } from '@lib/contract/types'

export interface CaveatFlag {
  key: string
  label: string
  tooltip: string
}

// STUB condition logic -- these thresholds/rules are placeholders wired to
// existing project findings (see memory/research_stats_validity_bugs.md and
// research_peakwidth_confound.md) so the UI surfaces the *shape* of each
// caveat now. The real per-row logic (joining ledger tier / atlas snap
// provenance / peak width) lands once the contract/backend expose those
// fields on FindingRow.
export function caveatFlagsFor(row: FindingRow): CaveatFlag[] {
  const flags: CaveatFlag[] = []

  if (row.strategy === 'nb_multi') {
    flags.push({
      key: 'omnibus-double-dip',
      label: '⚠ omnibus double-dip',
      tooltip: 'nb_multi is an omnibus test over the same cells used to call direction -- significance is inflated (double-dipping).',
    })
  }

  // STUB: real rule needs peak width from the ledger, not utr_class.
  if (row.utr_class === 'extended') {
    flags.push({
      key: 'width-confound',
      label: '⚠ width-confound',
      tooltip: 'Extended-UTR calls correlate strongly with raw peak width, not necessarily true 3’ shortening/lengthening.',
    })
  }

  // STUB: real rule needs atlas snap_distance_bp from the PAS ledger (joined
  // via pas_uid), not available on FindingRow yet.
  if (row.strategy === 'fisher' && row.qvalue < 0.01) {
    flags.push({
      key: 'atlas-circularity',
      label: '⚠ atlas-circularity',
      tooltip: 'High-confidence calls snapped to atlas PAS can look artificially precise; atlas precision is not independently validated.',
    })
  }

  return flags
}
