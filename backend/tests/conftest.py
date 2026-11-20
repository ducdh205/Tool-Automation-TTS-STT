import pytest

from backend.tests.helpers import build_mini_form


@pytest.fixture
def mini_form(tmp_path):
    return build_mini_form(tmp_path / "mini_form.xlsx")
