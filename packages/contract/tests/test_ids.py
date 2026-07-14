from __future__ import annotations

import pytest

from peakatail_contract.ids import cell_uid, cluster_uid, finding_uid, pas_summit_pos, pas_uid


class TestPasSummitPos:
    """Strand-aware 3'-summit position, per engine-team's E1 alignment
    (2026-07-14): pos = end - 1 if strand == '+' else start."""

    def test_plus_strand_uses_end_minus_one(self):
        assert pas_summit_pos(500, 1000, "+") == 999

    def test_minus_strand_uses_start(self):
        assert pas_summit_pos(500, 1000, "-") == 500

    def test_invalid_strand_rejected(self):
        with pytest.raises(ValueError):
            pas_summit_pos(500, 1000, "*")


class TestPasUid:
    def test_determinism(self):
        assert pas_uid("chr1", 500, 1000, "+") == pas_uid("chr1", 500, 1000, "+")

    def test_grammar_plus_strand(self):
        # pos = end - 1 = 999 on the '+' strand -- NOT the raw `end` (1000).
        assert pas_uid("chr1", 500, 1000, "+") == "chr1:999:+"

    def test_grammar_minus_strand(self):
        # pos = start = 500 on the '-' strand -- the biological 3'-end.
        assert pas_uid("chr1", 500, 1000, "-") == "chr1:500:-"

    def test_strand_disambiguation(self):
        # The specific B1 bug this ID exists to prevent: same interval,
        # different strand, must NOT collide.
        assert pas_uid("chr1", 500, 1000, "+") != pas_uid("chr1", 500, 1000, "-")

    def test_end_disambiguation(self):
        assert pas_uid("chr1", 500, 1000, "+") != pas_uid("chr1", 500, 1001, "+")

    def test_chrom_disambiguation(self):
        assert pas_uid("chr1", 500, 1000, "+") != pas_uid("chr2", 500, 1000, "+")

    def test_invalid_strand_rejected(self):
        with pytest.raises(ValueError):
            pas_uid("chr1", 500, 1000, "*")

    def test_chrom_with_separator_rejected(self):
        with pytest.raises(ValueError):
            pas_uid("chr1:foo", 500, 1000, "+")

    def test_end_coerced_to_int(self):
        assert pas_uid("chr1", "500", "1000", "+") == "chr1:999:+"


class TestCellUid:
    def test_determinism(self):
        assert cell_uid("ds1", "AAAA") == cell_uid("ds1", "AAAA")

    def test_grammar(self):
        assert cell_uid("ds1", "AAAA") == "ds1:AAAA"

    def test_dataset_disambiguation(self):
        # Same raw barcode, different dataset -- must not collide (the whole
        # point of namespacing barcodes per Data Controller Design §1).
        assert cell_uid("ds1", "AAAA") != cell_uid("ds2", "AAAA")

    def test_separator_in_field_rejected(self):
        with pytest.raises(ValueError):
            cell_uid("ds:1", "AAAA")
        with pytest.raises(ValueError):
            cell_uid("ds1", "AA:AA")


class TestClusterUid:
    def test_determinism(self):
        assert cluster_uid("ds1", "0") == cluster_uid("ds1", "0")

    def test_grammar(self):
        assert cluster_uid("ds1", "0") == "ds1:0"

    def test_dataset_disambiguation(self):
        # leiden cluster labels collide across datasets by construction
        # (Data Controller Design §1); cluster_uid must not.
        assert cluster_uid("ds1", "0") != cluster_uid("ds2", "0")

    def test_accepts_int_leiden(self):
        assert cluster_uid("ds1", 0) == "ds1:0"


class TestFindingUid:
    def test_determinism(self):
        a = finding_uid("TCell", "unified_1", "fisher", "cl_A_vs_cl_B", "chr1:1000:+")
        b = finding_uid("TCell", "unified_1", "fisher", "cl_A_vs_cl_B", "chr1:1000:+")
        assert a == b

    def test_distinct_strategy_no_collision(self):
        base = ("TCell", "unified_1", "cl_A_vs_cl_B", "chr1:1000:+")
        a = finding_uid(base[0], base[1], "fisher", base[2], base[3])
        b = finding_uid(base[0], base[1], "nb_pairwise", base[2], base[3])
        assert a != b

    def test_distinct_label_no_collision(self):
        # Simulates two different (untruncated) resolved labels that would
        # otherwise both truncate to the same 48-char directory name (D10):
        # finding_uid must still distinguish them because it uses the FULL
        # resolved label, not the truncated one.
        long_a = "CD8_TCell_activated_earlyresponse_subclusterA_extra"
        long_b = "CD8_TCell_activated_earlyresponse_subclusterB_extra"
        a = finding_uid(long_a, "unified_1", "fisher", "arm", "chr1:1000:+")
        b = finding_uid(long_b, "unified_1", "fisher", "arm", "chr1:1000:+")
        assert a != b

    def test_distinct_var_name_no_collision(self):
        # Guards against the B7 failure mode: two distinct var_names must
        # never collide just because a naive implementation used
        # var['gene_id'] (which can be NaN/shared) instead.
        a = finding_uid("TCell", "unified_1", "fisher", "arm", "chr1:1000:+")
        b = finding_uid("TCell", "unified_2", "fisher", "arm", "chr1:1000:+")
        assert a != b

    def test_distinct_pas_uid_no_collision(self):
        a = finding_uid("TCell", "unified_1", "fisher", "arm", "chr1:1000:+")
        b = finding_uid("TCell", "unified_1", "fisher", "arm", "chr1:1000:-")
        assert a != b

    def test_pas_uid_value_may_contain_separator(self):
        # pas_uid_value is exempt from the separator guard (it's always last).
        result = finding_uid("TCell", "unified_1", "fisher", "arm", "chr1:1000:+")
        assert result.endswith("chr1:1000:+")

    def test_other_fields_reject_separator(self):
        with pytest.raises(ValueError):
            finding_uid("T:Cell", "unified_1", "fisher", "arm", "chr1:1000:+")
        with pytest.raises(ValueError):
            finding_uid("TCell", "unified:1", "fisher", "arm", "chr1:1000:+")
        with pytest.raises(ValueError):
            finding_uid("TCell", "unified_1", "fisher", "arm:1", "chr1:1000:+")
