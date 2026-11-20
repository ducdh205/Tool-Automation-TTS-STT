from tts_stt_tool.config import Settings, load_settings, save_settings


def test_defaults_on_first_load(tmp_path):
    s = load_settings(tmp_path)
    assert s.data_dir == tmp_path
    assert s.max_regen == 3
    assert s.wer_threshold == 0.0
    assert s.reject_warn_ratio == 0.10
    assert s.wyoming_host == "127.0.0.1"
    assert s.wyoming_port == 10300
    assert s.stt_timeout_s == 30.0
    assert s.port == 8765
    assert s.voice == "Ngọc Huyền"


def test_roundtrip(tmp_path):
    s = load_settings(tmp_path)
    s.max_regen = 5
    s.voice = "Mai Anh"
    save_settings(s)
    s2 = load_settings(tmp_path)
    assert s2.max_regen == 5
    assert s2.voice == "Mai Anh"


def test_corrupt_file_gives_defaults(tmp_path):
    (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")
    assert load_settings(tmp_path).max_regen == 3


def test_unknown_keys_ignored(tmp_path):
    (tmp_path / "settings.json").write_text('{"max_regen": 2, "bogus": 1}', encoding="utf-8")
    s = load_settings(tmp_path)
    assert s.max_regen == 2
    assert not hasattr(s, "bogus")


def test_mutable_defaults_not_shared(tmp_path):
    a = Settings(data_dir=tmp_path)
    b = Settings(data_dir=tmp_path)
    a.wyoming_cmd.append("x")
    assert b.wyoming_cmd == []
