"""Export JSON Schema for every contract model.

This is what the hub frontend's `lib/contract` TS types are (later)
generated from (design spec §4 "Modules + repo boundary"). Output is one
file per model under ``schema/``, with deterministic (sorted-key) JSON so
diffs are clean across contract versions.
"""

from __future__ import annotations

import json
from pathlib import Path

from peakatail_contract import CONTRACT_VERSION
from peakatail_contract.models import (
    Artifact,
    CellLedgerRow,
    DatasetRef,
    FindingRow,
    LengthRow,
    PasLedgerRow,
    RunManifest,
)

#: Every model exported as a standalone JSON Schema file. Keep this list in
#: sync with peakatail_contract.models -- schema_export tests fail if a
#: model is added there and forgotten here.
MODELS = {
    "RunManifest": RunManifest,
    "DatasetRef": DatasetRef,
    "Artifact": Artifact,
    "PasLedgerRow": PasLedgerRow,
    "CellLedgerRow": CellLedgerRow,
    "FindingRow": FindingRow,
    "LengthRow": LengthRow,
}


def export_schemas(out_dir: Path) -> list[Path]:
    """Write one deterministic JSON Schema file per model into ``out_dir``.

    Returns the list of written paths. Idempotent: re-running with no model
    changes produces byte-identical files (sorted keys, trailing newline,
    fixed indent) so `git diff` on ``schema/*.json`` only shows real changes.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        schema["$id"] = f"https://peakatail.dev/contract/{CONTRACT_VERSION}/{name}.json"
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        written.append(path)
    return written


def main() -> None:
    here = Path(__file__).resolve()
    # packages/contract/src/peakatail_contract/schema_export.py -> packages/contract/schema
    default_out = here.parents[2] / "schema"
    written = export_schemas(default_out)
    for path in written:
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
