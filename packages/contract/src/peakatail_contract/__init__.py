"""peakatail-contract: the schema-only coupling layer between the PeakATail
engine and peakatail-hub.

Per spec §7a this package is intentionally dependency-light: pydantic models,
ID-minting helpers, and a cross-artifact ``validate()`` function only. No
anndata/h5py/scipy/scanpy/pysam. Everything that needs to *open* an h5ad/mtx
file lives in the sibling ``peakatail-io`` package (not this one).
"""

from peakatail_contract.models import (
    Artifact,
    CellLedgerRow,
    DatasetRef,
    Direction,
    Format,
    FindingRow,
    LengthRow,
    LengthStrategy,
    PasLedgerRow,
    RunManifest,
    Strategy,
    Tier,
)
from peakatail_contract.validate import ContractValidationError, validate

#: Single semver source of truth for the contract schema. Bump this whenever
#: any model field is added/removed/renamed in a backward-incompatible way.
#: ``RunManifest.contract_version`` defaults to this value, and
#: ``validate()`` checks manifests against it (see validate.py).
CONTRACT_VERSION = "0.1.0"

__all__ = [
    "CONTRACT_VERSION",
    "RunManifest",
    "DatasetRef",
    "Artifact",
    "PasLedgerRow",
    "CellLedgerRow",
    "FindingRow",
    "LengthRow",
    "Direction",
    "Format",
    "Strategy",
    "LengthStrategy",
    "Tier",
    "validate",
    "ContractValidationError",
]
