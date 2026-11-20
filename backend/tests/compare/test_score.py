import pytest

from tts_stt_tool.compare.score import WordOp, compare


def test_identical_is_correct():
    r = compare("Bật điều hòa", "bật điều hoà.")
    assert r.correct
    assert r.wer == 0
    assert r.cer == 0
    assert r.ref_norm == r.hyp_norm


def test_one_substitution():
    r = compare("mua sữa", "mua sửa")
    assert r.wer == 0.5
    assert not r.correct
    assert WordOp("sub", "sữa", "sửa") in r.ops
    assert WordOp("equal", "mua", "mua") in r.ops


def test_deletion_op():
    r = compare("bật đèn trần", "bật trần")
    assert r.ops == [WordOp("equal", "bật", "bật"), WordOp("del", "đèn", None), WordOp("equal", "trần", "trần")]


def test_insertion_op():
    r = compare("bật đèn", "bật đèn nhé")
    assert r.ops[-1] == WordOp("ins", None, "nhé")
    assert r.wer == 0.5


def test_threshold():
    assert compare("a b c d", "a b c x", wer_threshold=0.25).correct
    assert not compare("a b c d", "a b x x", wer_threshold=0.25).correct


def test_empty_hyp():
    r = compare("bật đèn", "")
    assert r.wer == 1.0
    assert r.cer == 1.0
    assert not r.correct
    assert [op.op for op in r.ops] == ["del", "del"]


def test_empty_ref_raises():
    with pytest.raises(ValueError):
        compare("  ...", "x")


def test_numbers_compare_equal():
    assert compare("Mở cửa kính 30%", "mở cửa kính ba mươi phần trăm").correct
