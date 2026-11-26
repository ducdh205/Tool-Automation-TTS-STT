import json

import pytest

from tts_stt_tool.device.profile import DEFAULT_PROFILE, AppProfile, get_profile, list_profiles, save_profile


def test_default_profile_values():
    p = AppProfile()
    assert p.name == "Vita Work (dev)"
    assert p.package == "com.vita.suite.dev"
    assert (p.open_label, p.stop_label, p.idle_label, p.close_label) == (
        "Nói để tạo việc", "Dừng nghe", "Bấm để nói", "Đóng")
    assert (p.pre_delay_s, p.post_delay_s) == (0.3, 1.0)
    assert p.discard_label == "Bỏ thay đổi"
    assert p.heard_prefix == "Bạn nói: "


def test_default_listed_when_empty(tmp_path):
    assert [p.name for p in list_profiles(tmp_path)] == [DEFAULT_PROFILE.name]


def test_save_and_get(tmp_path):
    save_profile(tmp_path, AppProfile(name="App B", package="com.b", open_label="Mic"))
    assert get_profile(tmp_path, "App B").open_label == "Mic"
    assert {p.name for p in list_profiles(tmp_path)} == {"App B", DEFAULT_PROFILE.name}


def test_saved_default_overrides(tmp_path):
    save_profile(tmp_path, AppProfile(post_delay_s=2.0))
    assert get_profile(tmp_path, DEFAULT_PROFILE.name).post_delay_s == 2.0
    assert len(list_profiles(tmp_path)) == 1


def test_corrupt_and_unknown_keys(tmp_path):
    (tmp_path / "bad.json").write_text("{nope", encoding="utf-8")
    (tmp_path / "x.json").write_text(json.dumps({"name": "X", "bogus": 1}), encoding="utf-8")
    names = {p.name for p in list_profiles(tmp_path)}
    assert "X" in names


def test_missing_profile(tmp_path):
    with pytest.raises(KeyError):
        get_profile(tmp_path, "nope")
