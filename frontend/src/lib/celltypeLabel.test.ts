import { describe, expect, it } from 'vitest'
import { celltypeLabel } from './celltypeLabel'

describe('celltypeLabel', () => {
  it('strips the CELL_TYPES_WANSLEEBEN_HOGAN_2013_ prefix and title-cases the remainder', () => {
    expect(celltypeLabel('CELL_TYPES_WANSLEEBEN_HOGAN_2013_MESENCHYAL')).toBe('Mesenchyal')
    expect(celltypeLabel('CELL_TYPES_WANSLEEBEN_HOGAN_2013_ACTIVATED_CD8T')).toBe('Activated CD8 T')
    expect(celltypeLabel('CELL_TYPES_WANSLEEBEN_HOGAN_2013_MACROPHAGE_M1')).toBe('Macrophage M1')
  })

  it('strips the lung_epithelial_lineage_signatures_ prefix', () => {
    expect(celltypeLabel('lung_epithelial_lineage_signatures_PNECS')).toBe('PNECs')
  })

  it('strips the stem_cell_signatures_merged_ prefix', () => {
    // "MAR" is <=3 chars and already all-caps in the source (a truncated
    // stratum label, bug D10 -- likely "MARGINAL" or similar cut short) --
    // kept as-is rather than mangled to "Mar", same rule that keeps
    // "NK"/"DC"/etc from becoming "Nk"/"Dc".
    expect(celltypeLabel('stem_cell_signatures_merged_NK_CELL_SPECIFIC_MAR')).toBe('NK Cell Specific MAR')
  })

  it('falls back to title-casing the whole id when no known prefix matches', () => {
    expect(celltypeLabel('some_unknown_signature_FOO_BAR')).toBe('Some Unknown Signature FOO BAR')
  })

  it('never returns an empty string, even for a degenerate id', () => {
    expect(celltypeLabel('CELL_TYPES_WANSLEEBEN_HOGAN_2013_')).toBe('CELL_TYPES_WANSLEEBEN_HOGAN_2013_')
  })
})
