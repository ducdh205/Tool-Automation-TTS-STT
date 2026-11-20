from tts_stt_tool.report.layout import case_folders, safe_component, turn_prefix


def r(rid, sheet, tc, turn, status, row):
    return {"id": rid, "sheet": sheet, "tc_id": tc, "turn": turn, "status": status, "source_row": row}


def test_case_folders_turns_share_folder_duplicates_split():
    rs = [r(1, "S", "TC1", "1", "Đúng", 5), r(2, "S", "TC1", "2", "Sai", 6), r(3, "S", "TC1", "1", "Đúng", 9)]
    assert case_folders(rs) == {1: "S/FAIL_TC1", 2: "S/FAIL_TC1", 3: "S/PASS_TC1_2"}


def test_case_folders_sanitize_trailing_space_and_slash():
    rs = [r(1, "Unlock Charging Port via Voice ", "TC/01:a", "1", "Lỗi thao tác", 5)]
    assert case_folders(rs) == {1: "Unlock Charging Port via Voice/LOI_TC_01_a"}


def test_prefix_precedence_pending_and_defaults():
    rs = [
        r(1, "S", "A", "1", "Đúng", 5), r(2, "S", "A", "2", "Chờ", 6),
        r(3, "S", "B", "1", "Lỗi thao tác", 7), r(4, "S", "B", "2", "Sai", 8),
        r(5, "", "C", "1", "Đúng", 9),
        r(6, "S", "", "1", "Sai", 12),
    ]
    assert case_folders(rs) == {1: "S/CHUA_A", 2: "S/CHUA_A", 3: "S/FAIL_B", 4: "S/FAIL_B",
                                5: "Dữ liệu/PASS_C", 6: "S/FAIL_dong12"}


def test_case_folders_order_does_not_depend_on_input_order():
    rs = [r(3, "S", "TC1", "1", "Đúng", 9), r(1, "S", "TC1", "1", "Sai", 5)]
    assert case_folders(rs) == {1: "S/FAIL_TC1", 3: "S/PASS_TC1_2"}


def test_safe_component():
    assert safe_component('a<b>c:"d"/e\\f|g?h*') == "a_b_c__d__e_f_g_h_"
    assert safe_component("name. . ") == "name"
    assert safe_component("CON") == "_CON"
    assert safe_component("com1") == "_com1"
    assert safe_component("") == "_"
    assert safe_component("a\tb") == "a_b"


def test_turn_prefix():
    assert [turn_prefix(t) for t in ("2", "Bước 3", "", "1.0", None)] == ["luot2_", "luot3_", "luot1_", "luot1_", "luot1_"]
