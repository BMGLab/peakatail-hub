"""Pure-stdlib streaming GTF parsing for the geneview endpoints.

Ported from PeakATail's `ema/viz/_gene_track_helpers.py` (the sibling
bioinformatics package's own gene-track renderer: `load_gene_name_from_gtf`
/ `load_isoforms_for_gene`), reimplemented here so this hub does not import
`ema` as a dependency. Same crude-but-sufficient approach: stream the GTF
once, extract `gene_id "..."` / `transcript_id "..."` / `gene_name "..."`
attributes with plain string search rather than a full GTF/GFF attribute
grammar -- real GTF emitters always quote attribute values and never embed
an unescaped `"` inside one, so this is safe and avoids adding a parsing
dependency (spec §7a: no new deps).

GTF is 1-based, closed-interval (`start`/`end` both inclusive); every other
coordinate this hub hands to the frontend (pas_ledger, pasbed.bed) is
BED-style 0-based half-open, so exon coordinates are converted here at
parse time (`start - 1, end`) -- callers of `load_isoforms` never see raw
1-based GTF coordinates.

Both functions are best-effort and NEVER raise: a missing/unreadable GTF or
a gene_id absent from it is exactly as common as "no GTF configured at all"
(v1 fixtures/early real runs), and a gene-track panel missing its isoform
structure is a degraded-but-still-useful view, not a 500.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def _gtf_attr(attr_field: str, key: str) -> str:
    """Extract a single attribute value from a GTF column-9 attribute field.

    Crude `key "value"` extraction (no full attribute grammar) -- mirrors
    the ema reference implementation exactly.
    """
    needle = f'{key} "'
    i = attr_field.find(needle)
    if i < 0:
        return ""
    j = attr_field.find('"', i + len(needle))
    if j < 0:
        return ""
    return attr_field[i + len(needle) : j]


def load_gene_name(gtf_path: Path, gene_id: str) -> str:
    """Return the `gene_name` attribute for `gene_id` from `gtf_path`.

    Streams the GTF, stopping at the first line whose attributes mention
    `gene_id "<gene_id>"` (gene_name is identical across every row for one
    gene, so the first hit suffices; the reference row need not be a
    `gene`-feature row).

    Returns `""` -- never raises -- if the file is missing/unreadable
    (`OSError`, logged as a warning) or `gene_id` isn't found in it.
    """
    needle = f'gene_id "{gene_id}"'
    try:
        with open(gtf_path) as fh:
            for line in fh:
                if line.startswith("#") or not line.strip():
                    continue
                if needle not in line:
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 9:
                    continue
                name = _gtf_attr(parts[8], "gene_name")
                if name:
                    return name
    except OSError as exc:
        log.warning("load_gene_name: could not read %s: %s", gtf_path, exc)
    return ""


def load_isoforms(
    gtf_path: Path, gene_id: str, feature_type: str = "exon"
) -> list[tuple[str, list[tuple[int, int]]]]:
    """Return `[(transcript_id, [(exon_start, exon_end), ...]), ...]` for
    every `feature_type` row belonging to `gene_id` in `gtf_path`.

    Exon coordinates are converted from GTF's 1-based closed interval to
    BED-style 0-based half-open (`start - 1, end`) at parse time, and each
    transcript's exon list is returned sorted ascending by coordinate.

    Returns `[]` -- never raises -- if the file is missing/unreadable
    (`OSError`, logged as a warning) or `gene_id` has no matching rows.
    """
    isoforms: dict[str, list[tuple[int, int]]] = {}
    gene_id_str = str(gene_id)
    try:
        with open(gtf_path) as fh:
            for line in fh:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 9 or parts[2] != feature_type:
                    continue
                attrs = parts[8]
                if gene_id_str not in attrs:
                    continue
                # crude attribute parse -- see _gtf_attr docstring
                gid = _gtf_attr(attrs, "gene_id")
                if gid != gene_id_str:
                    continue
                tid = _gtf_attr(attrs, "transcript_id") or "unknown"
                isoforms.setdefault(tid, []).append((int(parts[3]) - 1, int(parts[4])))
    except OSError as exc:
        log.warning("load_isoforms: could not read %s: %s", gtf_path, exc)
        return []
    return [(t, sorted(exons)) for t, exons in isoforms.items()]
