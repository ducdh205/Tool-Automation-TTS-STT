import pytest

from backend.tests.helpers import SAMPLE_XLSX
from tts_stt_tool.input.generic import ColumnMapping, read_items, sheet_names
from tts_stt_tool.input.testcase_form import InputError


def test_missing_file_raises_input_error(tmp_path):
    with pytest.raises(InputError):
        sheet_names(tmp_path / "nope.xlsx")


@pytest.mark.sample
@pytest.mark.skipif(not SAMPLE_XLSX.exists(), reason="sample file missing")
def test_sample_file_has_3986_items():
    m = ColumnMapping(text_col="Câu nói (utterance)", header_row=4, id_col="TC_ID")
    sheets = []
    for name in sheet_names(SAMPLE_XLSX):
        try:
            if read_items(SAMPLE_XLSX, [name], m):
                sheets.append(name)
        except InputError:
            pass
    assert len(sheets) == 14
    assert len(read_items(SAMPLE_XLSX, sheets, m)) == 3986
