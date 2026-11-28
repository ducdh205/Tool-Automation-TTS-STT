from tts_stt_tool.config import Settings, load_settings, save_settings


def test_defaults_on_first_load(tmp_path):
    s = load_settings(tmp_path)
    assert s.data_dir == tmp_path
    assert not hasattr(s, "max_regen")  # removed: no pipeline read it
    assert s.wer_threshold == 0.0
    assert s.reject_warn_ratio == 0.10
    assert s.wyoming_host == "127.0.0.1"
    assert s.wyoming_port == 10300
    assert s.stt_timeout_s == 30.0
    assert s.port == 8765
    assert s.voice == "Ngọc Huyền"


def test_roundtrip(tmp_path):
    s = load_settings(tmp_path)
    s.wer_threshold = 0.2
    s.voice = "Mai Anh"
    save_settings(s)
    s2 = load_settings(tmp_path)
    assert s2.wer_threshold == 0.2
    assert s2.voice == "Mai Anh"


def test_corrupt_file_gives_defaults(tmp_path):
    (tmp_path / "settings.json").write_text("{not json", encoding="utf-8")
    assert load_settings(tmp_path).wer_threshold == 0.0


def test_unknown_keys_ignored(tmp_path):
    (tmp_path / "settings.json").write_text('{"wer_threshold": 0.3, "bogus": 1}', encoding="utf-8")
    s = load_settings(tmp_path)
    assert s.wer_threshold == 0.3
    assert not hasattr(s, "bogus")


def test_old_file_with_max_regen_loads_and_drops_it(tmp_path):
    """settings.json written before max_regen was removed: still loads; the next save forgets it."""
    (tmp_path / "settings.json").write_text('{"max_regen": 3, "voice": "Mai Anh"}', encoding="utf-8")
    s = load_settings(tmp_path)
    assert s.voice == "Mai Anh"
    save_settings(s)
    assert "max_regen" not in (tmp_path / "settings.json").read_text(encoding="utf-8")


def test_mutable_defaults_not_shared(tmp_path):
    a = Settings(data_dir=tmp_path)
    b = Settings(data_dir=tmp_path)
    a.wyoming_cmd.append("x")
    assert b.wyoming_cmd == []


def test_tts_device_default_and_roundtrip(tmp_path):
    s = load_settings(tmp_path)
    assert s.tts_device == "cpu"
    s.tts_device = "cuda"
    save_settings(s)
    assert load_settings(tmp_path).tts_device == "cuda"
