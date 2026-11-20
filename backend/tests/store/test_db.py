import pytest

from tts_stt_tool.compare.score import compare
from tts_stt_tool.models import InputItem
from tts_stt_tool.store.db import ItemStatus, Store

USER = "👤 Người dùng"


def _item(tc, text, speaker=USER, sheet="S1"):
    return InputItem(sheet=sheet, tc_id=tc, turn="1", feature="f", priority="P1", region="BAC-HN",
                     speaker=speaker, text_raw=text, expected="exp", source_row=5)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "tool.db")


@pytest.fixture
def set_id(store):
    items = [
        _item("TC-1", "Hey Vita, bật đèn trần"),
        _item("TC-2", "Xe chuyển số D", speaker="🚗 Hệ thống (sự kiện)"),
        _item("TC-3", "Hey Vita"),
    ]
    return store.create_audio_set("bộ 1", "file.xlsx", ["S1"], "Ngọc Huyền", items)


def test_create_classifies_items(store, set_id):
    assert store.summary(set_id) == {ItemStatus.PENDING.value: 1, ItemStatus.SKIPPED.value: 2}
    items = store.get_items(set_id)
    assert [i["text_tts"] for i in items] == ["bật đèn trần", None, None]
    assert items[1]["skip_reason"] == "Dòng hệ thống"
    assert items[1]["enabled"] == 0
    assert items[0]["text_raw"] == "Hey Vita, bật đèn trần"


def test_get_items_filter_by_status(store, set_id):
    assert len(store.get_items(set_id, ItemStatus.SKIPPED)) == 2


def test_list_audio_sets(store, set_id):
    sets = store.list_audio_sets()
    assert sets[0]["id"] == set_id
    assert sets[0]["name"] == "bộ 1"
    assert sets[0]["sheets"] == ["S1"]
    assert sets[0]["voice"] == "Ngọc Huyền"


def test_set_item_text_reenables_skipped(store, set_id):
    skipped = store.get_items(set_id, ItemStatus.SKIPPED)[0]
    store.set_item_text(skipped["id"], "Bật đèn")
    row = store.get_item(skipped["id"])
    assert row["status"] == ItemStatus.PENDING.value
    assert row["enabled"] == 1
    assert row["skip_reason"] is None
    assert row["text_tts"] == "Bật đèn"


def test_set_item_text_resets_audio_and_verify(store, set_id):
    item = store.get_items(set_id, ItemStatus.PENDING)[0]
    store.record_generated(item["id"], "a.wav", 1)
    store.record_verify(item["id"], "bật đèn trần", compare("bật đèn trần", "bật đèn trần"), ItemStatus.PASSED)
    store.set_item_text(item["id"], "bật đèn trần nhé")
    row = store.get_item(item["id"])
    assert row["status"] == ItemStatus.PENDING.value
    assert row["audio_path"] is None
    assert row["ref_text"] is None
    assert row["wer"] is None
    assert row["attempts"] == 0


def test_record_verify_saves_scores(store, set_id):
    item = store.get_items(set_id, ItemStatus.PENDING)[0]
    store.record_generated(item["id"], "a.wav", 2)
    r = compare("mua sữa", "mua sửa")
    store.record_verify(item["id"], "mua sửa", r, ItemStatus.AUDIO_FAILED)
    row = store.get_item(item["id"])
    assert row["wer"] == 0.5
    assert row["ref_text"] == "mua sửa"
    assert row["attempts"] == 2
    assert {"op": "sub", "ref": "sữa", "hyp": "sửa"} in row["ops"]
    assert row["status"] == ItemStatus.AUDIO_FAILED.value


def test_pending_for_block1(store, set_id):
    item = store.get_items(set_id, ItemStatus.PENDING)[0]
    assert [i["id"] for i in store.pending_for_block1(set_id)] == [item["id"]]
    store.record_error(item["id"], "boom")
    assert store.get_item(item["id"])["status"] == ItemStatus.ERROR.value
    assert len(store.pending_for_block1(set_id)) == 1  # errors are retried
    store.set_enabled(item["id"], False)
    assert store.pending_for_block1(set_id) == []


def test_persists_across_instances(tmp_path, set_id, store):
    again = Store(tmp_path / "tool.db")
    assert again.summary(set_id) == store.summary(set_id)
