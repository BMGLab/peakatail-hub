from __future__ import annotations

import json

from peakatail_contract.schema_export import MODELS, export_schemas


def test_export_is_deterministic(tmp_path):
    out1 = export_schemas(tmp_path / "a")
    out2 = export_schemas(tmp_path / "b")
    assert len(out1) == len(out2) == len(MODELS)
    for p1, p2 in zip(sorted(out1), sorted(out2)):
        assert p1.name == p2.name
        assert p1.read_text() == p2.read_text()


def test_every_model_has_schema_file(tmp_path):
    out = export_schemas(tmp_path)
    names = {p.name for p in out}
    for model_name in MODELS:
        assert f"{model_name}.json" in names


def test_schema_is_valid_json_with_sorted_keys(tmp_path):
    out = export_schemas(tmp_path)
    for path in out:
        text = path.read_text()
        data = json.loads(text)
        assert isinstance(data, dict)
        # re-dumping with sort_keys should be byte-identical (minus trailing newline)
        assert json.dumps(data, indent=2, sort_keys=True) + "\n" == text
