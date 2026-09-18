import pytest
from app.tools.builtin import safe_eval
import ast


def test_calculator():
    assert safe_eval(ast.parse("2 + 3 * 4", mode="eval").body) == 14


def test_reject_names():
    with pytest.raises(ValueError):
        safe_eval(ast.parse("__import__('os')", mode="eval").body)
