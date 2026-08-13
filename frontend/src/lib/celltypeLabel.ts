// Clean, human-readable cell-type display names (2026-08-14). Real celltype
// IDs are raw signature/stratum identifiers -- e.g.
// "CELL_TYPES_WANSLEEBEN_HOGAN_2013_MESENCHYAL",
// "lung_epithelial_lineage_signatures_PNECS",
// "stem_cell_signatures_merged_NK_CELL_SPECIFIC_MAR" -- unreadable as
// headers/labels. `celltypeLabel()` derives a short display name by
// stripping the known signature-source prefix and title-casing the
// remainder (with a few biology-abbreviation overrides so "NK"/"CD8T"/etc
// don't get mangled to "Nk"/"Cd8t"). Deterministic, no network/lookup --
// the ORIGINAL id is never discarded: every call site keeps using the full
// id as the stable key/query param/tooltip and only swaps in the label for
// display text.
//
// This is a display-only cosmetic transform over free-text stratum labels
// that are occasionally truncated at the source (bug D10, ema/provenance.py
// -- e.g. "...ENDOTH"/"...REGUL" are real, already-truncated ids, not a bug
// in this function) -- it cannot recover characters the source never had.

const KNOWN_PREFIXES: RegExp[] = [
  /^CELL_TYPES_WANSLEEBEN_HOGAN_2013_/,
  /^lung_epithelial_lineage_signatures_/,
  /^stem_cell_signatures_merged_/,
]

// Words that must NOT go through plain title-casing (acronyms/compound
// biology terms) -- keys are the UPPERCASED word as it appears in the raw
// id, values are the exact display text to use instead.
const WORD_OVERRIDES: Record<string, string> = {
  NK: 'NK',
  DC: 'DC',
  AE2: 'AE2',
  M1: 'M1',
  M2: 'M2',
  CD4T: 'CD4 T',
  CD8T: 'CD8 T',
  PNECS: 'PNECs',
}

function titleCaseWord(word: string): string {
  const upper = word.toUpperCase()
  if (upper in WORD_OVERRIDES) return WORD_OVERRIDES[upper]!
  // A short (<=3 char) word that's ALREADY all-caps in the source is very
  // likely an acronym we don't have an explicit override for yet (e.g. a
  // future signature family) -- keep it as-is rather than mangling it to
  // e.g. "Dc" -> "Dc" reads worse than "DC".
  if (word.length <= 3 && word === upper) return word
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
}

/** Derives a clean display label from a raw celltype/stratum id. Always
 * returns a non-empty string (falls back to the id itself if stripping the
 * prefix would leave nothing). Never call sites should stop keeping the
 * original id around too -- this is display text only, not a replacement
 * identifier (celltype ids are used as query params / React keys / API
 * path segments elsewhere and must stay exactly as indexed). */
export function celltypeLabel(id: string): string {
  let rest = id
  for (const prefix of KNOWN_PREFIXES) {
    if (prefix.test(rest)) {
      rest = rest.replace(prefix, '')
      break
    }
  }
  if (!rest) return id
  const words = rest.split(/[_\s]+/).filter(Boolean)
  if (words.length === 0) return id
  return words.map(titleCaseWord).join(' ')
}
