from __future__ import annotations

from pathlib import Path

import pytest

from peakatail_io import Run

CONTRACT_FIXTURES = Path(__file__).resolve().parents[2] / "contract" / "fixtures"


@pytest.fixture()
def contract_run() -> Run:
    """The real `packages/contract/fixtures` run, built and committed by the
    sibling contract agent -- this is the intended integration point (see
    packages/io/README.md and the task's "fixtures-first" instructions).
    """
    return Run.from_dir(CONTRACT_FIXTURES)
