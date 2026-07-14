"""Cross-artifact validation for a contract-conformant run.

Deliberately dependency-light (spec §7a): this module accepts plain
sequences of the pydantic row models (or dict-likes pydantic can parse),
never a DataFrame or an open h5ad handle. Anything that needs to *read*
`clusters.h5ad` (to get ``n_vars``) lives in ``peakatail-io``; callers here
pass that count in as a plain int (``n_vars_clusters_h5ad``).

This intentionally mirrors the split described in frontend-design spec §7a:
peakatail-contract knows the *shape* of the data and the invariants it must
satisfy; it never opens a run directory itself.
"""

from __future__ import annotations

from collections.abc import Sequence

from peakatail_contract.models import CellLedgerRow, FindingRow, LengthRow, PasLedgerRow, RunManifest


class ContractValidationError(Exception):
    """Raised by :func:`validate` with EVERY violation found, not just the first.

    ``errors`` is the full list of human-readable violation strings;
    ``str(exc)`` renders them newline-joined for convenient logging/printing.
    """

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def _major(version: str) -> str:
    return version.split(".", 1)[0]


def validate(
    manifest: RunManifest,
    pas_ledger: Sequence[PasLedgerRow],
    cell_ledger: Sequence[CellLedgerRow] | None = None,
    findings: Sequence[FindingRow] | None = None,
    length_rows: Sequence[LengthRow] | None = None,
    n_vars_clusters_h5ad: int | None = None,
    required_artifact_stages: Sequence[str] | None = None,
    contract_version: str = "0.1.0",
) -> None:
    """Validate a run's manifest + tables against the contract.

    Checks performed (accumulates ALL violations before raising):

    1. **Required artifacts present** -- if ``required_artifact_stages`` is
       given, every stage in it must have >=1 matching ``Artifact`` in
       ``manifest.artifacts``.
    2. **Schema/version compatibility** -- ``manifest.contract_version`` and
       every ``Artifact.schema_version`` must share a MAJOR version with the
       installed contract (``contract_version`` param, defaults to
       ``CONTRACT_VERSION``). A major-version mismatch means the reader and
       writer disagree on the schema shape and must not be silently trusted.
    3. **Referential integrity** -- every ``FindingRow.pas_uid`` and every
       populated ``LengthRow.pas_uid`` must exist in ``pas_ledger``; every
       ``LengthRow.cell_uid`` must exist in ``cell_ledger`` (if provided).
    4. **The core invariant** (Data Controller Design §2 / spec §5):
       ``rows(pas_ledger where dropped_at == "") == n_vars(clusters.h5ad)``.
       Only checked when ``n_vars_clusters_h5ad`` is supplied (the contract
       itself cannot open the h5ad -- see module docstring).

    Raises :class:`ContractValidationError` listing every violation found.
    Returns ``None`` (no exception) if the run is fully consistent.
    """
    errors: list[str] = []

    # 1. required artifacts present
    if required_artifact_stages:
        present_stages = {a.stage for a in manifest.artifacts}
        for stage in required_artifact_stages:
            if stage not in present_stages:
                errors.append(f"missing required artifact for stage={stage!r} (manifest has stages={sorted(present_stages)})")

    # 2. schema/version compatibility
    want_major = _major(contract_version)
    if _major(manifest.contract_version) != want_major:
        errors.append(
            f"manifest.contract_version={manifest.contract_version!r} has a different "
            f"major version than the installed contract ({contract_version!r})"
        )
    for artifact in manifest.artifacts:
        if _major(artifact.schema_version) != want_major:
            errors.append(
                f"artifact {artifact.path!r} (stage={artifact.stage!r}) has "
                f"schema_version={artifact.schema_version!r}, incompatible with "
                f"installed contract major version {want_major!r}"
            )

    # 3. referential integrity
    pas_uids = {row.pas_uid for row in pas_ledger}
    if findings:
        for row in findings:
            if row.pas_uid not in pas_uids:
                errors.append(f"FindingRow.finding_uid={row.finding_uid!r} references unknown pas_uid={row.pas_uid!r} (not in pas_ledger)")
            if not row.canonical_cluster:
                errors.append(f"FindingRow.finding_uid={row.finding_uid!r} has empty canonical_cluster")

    cell_uids = {row.cell_uid for row in cell_ledger} if cell_ledger else None
    if length_rows:
        for i, row in enumerate(length_rows):
            if row.pas_uid is not None and row.pas_uid not in pas_uids:
                errors.append(f"LengthRow[{i}] (strategy={row.strategy}, gene_id={row.gene_id!r}) references unknown pas_uid={row.pas_uid!r}")
            if cell_uids is not None and row.cell_uid not in cell_uids:
                errors.append(f"LengthRow[{i}] (strategy={row.strategy}, gene_id={row.gene_id!r}) references unknown cell_uid={row.cell_uid!r} (not in cell_ledger)")

    # 4. the core invariant
    if n_vars_clusters_h5ad is not None:
        n_surviving = sum(1 for row in pas_ledger if row.dropped_at == "")
        if n_surviving != n_vars_clusters_h5ad:
            errors.append(
                "invariant violated: rows(pas_ledger where dropped_at=='') "
                f"= {n_surviving} != n_vars(clusters.h5ad) = {n_vars_clusters_h5ad}"
            )

    if errors:
        raise ContractValidationError(errors)
