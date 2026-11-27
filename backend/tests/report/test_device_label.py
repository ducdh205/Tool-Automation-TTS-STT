from tts_stt_tool.report.device_label import device_tag, platform_label


def test_stored_platform_wins():
    assert platform_label({"platform": "ios", "serial": "abc"}) == "iPhone"
    assert platform_label({"platform": "android", "serial": "00008120-000C09D8266B601E"}) == "Android"


def test_old_runs_guess_from_the_serial():
    assert platform_label({"serial": "00008120-000C09D8266B601E"}) == "iPhone"  # iPhone UDID
    assert platform_label({"serial": "cqqcoz49dmsspjnr"}) == "Android"
    assert platform_label({}) == "Android"


def test_device_tag_names_platform_and_phone():
    assert device_tag({"platform": "android", "device_model": "22120RN86G", "serial": "S"}) == "Android_22120RN86G"
    assert device_tag({"platform": "ios", "device_model": "iPhone 15", "serial": "U"}) == "iPhone_iPhone 15"
    assert device_tag({"platform": "ios", "device_model": None, "serial": "U1"}) == "iPhone_U1"
