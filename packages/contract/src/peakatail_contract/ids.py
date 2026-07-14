"""Surrogate-key (ID) grammar for cross-artifact joins.

Every ID in this module is a **pure function of already-known, stable
inputs** -- no lookups, no run-time state, no randomness. That's what makes
them safe to re-mint independently by the engine indexer, the hub indexer,
and any test fixture, and still agree byte-for-byte.

Design note (Data Controller Design §4a superseded by frontend-design spec
§7d/§7g): the Data Controller Design draft proposed run-scoped IDs
(``pas_uid={run}:{ds}:{pas_id}``, ``finding_uid={arm}:{celltype}:{gene_id}``).
Those are REJECTED here in favor of the content-addressed forms mandated by
§7d/§7g, because:

* ``pas_id`` is a small run-local integer that is **re-minted 2-3 times**
  across the pipeline (peak-calling -> unify -> annotate) and is known to
  **collide across strand** (bug B1: ``pas_merge.py:186`` keys counts on
  ``(dataset_id, pas_id)`` with no strand component). A run-scoped
  ``pas_uid`` built on top of that integer inherits the collision. A
  content-addressed key built from genomic coordinates does not.
* raw ``celltype`` strings are directory-derived and get **silently
  truncated to 48 characters** by the OS/filesystem layer (bug D10) --
  two different strata can truncate to the same on-disk name. Minting an
  ID from the truncated name would silently merge distinct findings.
* ``var['gene_id']`` in the concatenated/report h5ad is **~59% NaN**
  (bug B7, verified: 18368/30919 vars NaN on a real run) because it is a
  column carried through concat, not the index. Joining or minting keys
  on that column silently drops the majority of real genes. ``var_names``
  (the h5ad index) is always populated and is the correct join key.
"""

from __future__ import annotations

_SEP = ":"


def _check_no_sep(name: str, value: str) -> None:
    """Guard against ambiguous IDs: none of our fields may contain the
    separator, or two distinct inputs could mint the same joined string
    (e.g. ``("a:b", "c")`` vs ``("a", "b:c")``).
    """
    if _SEP in value:
        raise ValueError(
            f"{name}={value!r} contains the ID separator {_SEP!r}; "
            "this would make the minted ID ambiguous/collision-prone."
        )


def pas_uid(chrom: str, end: int, strand: str) -> str:
    """Content-addressed PAS identifier: ``{chrom}:{end}:{strand}``.

    NOT ``{run}:{ds}:{pas_id}`` (superseded, see module docstring). Using the
    3'-end coordinate + strand makes the ID stable across re-runs, re-unifies,
    and even across datasets that call the *same* underlying PAS -- exactly
    the E1 "strand-safe merge key" fix in Data Controller Design §5.

    Strand is a required, distinct field (not folded into ``end``) so that
    ``chr1:1000:+`` and ``chr1:1000:-`` never collide -- this is the specific
    B1 bug (pos/neg strand PAS numbered from 1 independently) this ID grammar
    exists to prevent.
    """
    if strand not in ("+", "-"):
        raise ValueError(f"strand must be '+' or '-', got {strand!r}")
    _check_no_sep("chrom", chrom)
    return f"{chrom}{_SEP}{int(end)}{_SEP}{strand}"


def cell_uid(dataset_id: str, barcode: str) -> str:
    """Namespaced cell identifier: ``{dataset_id}:{barcode}``.

    Matches the "namespaced barcode" already used as the one reliable
    cross-artifact cell key in the real pipeline (Data Controller Design
    §1, ``"<ds>_<cb>"``) -- we standardize the separator to ``:`` here for
    consistency with the other *_uid functions, rather than inventing a new
    scheme.
    """
    _check_no_sep("dataset_id", dataset_id)
    _check_no_sep("barcode", barcode)
    return f"{dataset_id}{_SEP}{barcode}"


def cluster_uid(dataset_id: str, leiden: str) -> str:
    """Dataset-scoped cluster identifier: ``{dataset_id}:{leiden}``.

    ``leiden`` cluster labels are per-sample and collide across datasets
    (Data Controller Design §1/§3 bug context, "Cluster" row). This makes
    the collision explicit and joinable rather than silent. It is
    distinct from ``canonical_cluster`` (the cross-dataset-aligned label
    produced by ``switch match`` / bug B6) -- callers needing cross-sample
    comparability must use the manifest's ``stratum_to_label``-resolved
    canonical cluster, not this raw per-dataset ID.
    """
    _check_no_sep("dataset_id", dataset_id)
    _check_no_sep("leiden", str(leiden))
    return f"{dataset_id}{_SEP}{leiden}"


def finding_uid(
    resolved_label: str,
    var_name: str,
    strategy: str,
    arm: str,
    pas_uid_value: str,
) -> str:
    """Mint the ``finding_uid`` for one row of ``findings_long``.

    Per spec §7g, this MUST be minted from:

    * ``resolved_label`` -- the manifest-resolved label obtained via
      ``RunManifest.stratum_to_label``, e.g. the full celltype/stratum
      name. Callers must NOT pass the raw, possibly-48-char-truncated
      directory name (bug D10) here.
    * ``var_name`` -- the stable identifier taken from the h5ad's
      ``var_names`` index. Callers must NOT pass ``var['gene_id']``
      (bug B7, ~59% NaN).

    ``strategy`` (fisher/nb_pairwise/nb_multi) and ``arm`` (the analysis
    arm/comparison, e.g. a cluster-pair or stage label) plus ``pas_uid_value``
    (this row's content-addressed PAS ID, see :func:`pas_uid`) make the ID
    unique per PAS x comparison x strategy, matching the long-format grain
    of ``FindingRow`` (one row per PAS x comparison x strategy -- see
    models.py).

    This supersedes the Data Controller Design §4a draft grammar
    ``finding_uid={arm}:{celltype}:{gene_id}``, which used exactly the two
    unsafe raw strings this function forbids.

    Note: ``pas_uid_value`` is itself a colon-joined ID (``chrom:end:strand``,
    see :func:`pas_uid`) and is intentionally exempt from the separator guard
    below -- it is always the *last* field in the join, so splitting the
    other four (separator-free) fields off the front with
    ``str.split(":", maxsplit=4)`` still recovers an unambiguous
    ``pas_uid_value`` remainder.
    """
    for name, value in (
        ("resolved_label", resolved_label),
        ("var_name", var_name),
        ("strategy", strategy),
        ("arm", arm),
    ):
        _check_no_sep(name, str(value))
    return _SEP.join([arm, strategy, resolved_label, var_name, pas_uid_value])
