"""Unit tests for `peakatail_hub.gtf` -- the pure-stdlib GTF reader, tested
directly against `packages/contract/fixtures/genes.gtf` rather than a
throwaway inline fixture, so a regeneration of that fixture (via
`make_fixtures.py::_write_gtf`) exercises the exact same reader this test
suite asserts against.
"""

from __future__ import annotations

from pathlib import Path

from peakatail_hub import gtf

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "packages" / "contract" / "fixtures"
GTF_PATH = FIXTURES_DIR / "genes.gtf"


def test_load_gene_name_found():
    assert gtf.load_gene_name(GTF_PATH, "ENSG00000000001") == "TESTA1"
    assert gtf.load_gene_name(GTF_PATH, "ENSG00000000002") == "TESTB2"


def test_load_gene_name_not_found_returns_empty_string():
    assert gtf.load_gene_name(GTF_PATH, "ENSG_NOT_A_GENE") == ""


def test_load_gene_name_missing_file_returns_empty_string():
    assert gtf.load_gene_name(FIXTURES_DIR / "does_not_exist.gtf", "ENSG00000000001") == ""


def test_load_isoforms_found_two_transcripts_with_correct_exon_coords():
    isoforms = gtf.load_isoforms(GTF_PATH, "ENSG00000000001")
    assert len(isoforms) == 2

    by_id = dict(isoforms)
    assert set(by_id) == {"ENST00000000001", "ENST00000000002"}

    # Long/distal isoform: terminal exon 951-1500 (1-based) -> (950, 1500)
    # BED half-open -- covers both PAS (chr1:999-1000 and chr1:1499-1500).
    assert by_id["ENST00000000001"] == [(850, 900), (950, 1500)]
    # Short/proximal isoform: terminal exon 951-1000 (1-based) -> (950, 1000)
    # -- covers only the proximal PAS (chr1:999-1000).
    assert by_id["ENST00000000002"] == [(850, 900), (950, 1000)]


def test_load_isoforms_minus_strand_gene():
    isoforms = gtf.load_isoforms(GTF_PATH, "ENSG00000000002")
    by_id = dict(isoforms)
    assert set(by_id) == {"ENST00000000003", "ENST00000000004"}
    assert by_id["ENST00000000003"] == [(4999, 5400), (5450, 5500)]
    assert by_id["ENST00000000004"] == [(5350, 5400), (5450, 5500)]


def test_load_isoforms_gene_not_in_file_returns_empty_list():
    assert gtf.load_isoforms(GTF_PATH, "ENSG_NOT_A_GENE") == []


def test_load_isoforms_missing_file_returns_empty_list():
    assert gtf.load_isoforms(FIXTURES_DIR / "does_not_exist.gtf", "ENSG00000000001") == []
