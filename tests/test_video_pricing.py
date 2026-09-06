import pytest
from nalu_runtime.repository import ConflictError
from nalu_runtime.video_pricing import parse_rates

PRICE_HTML = """<table><tr><td><code>seedance-2.0-pro</code></td><td>$0.26 / sec</td><td>26 Credits / sec</td></tr>
<tr><td>seedance-2.0-fast</td><td>$0.22 / sec</td><td>22 Credits / sec</td></tr></table>"""


def test_official_table_units_are_consistent():
    assert parse_rates(PRICE_HTML) == {"seedance-2.0-pro": 26, "seedance-2.0-fast": 22}


@pytest.mark.parametrize("html", ["<html>Login</html>", PRICE_HTML + PRICE_HTML,
    PRICE_HTML.replace("26 Credits", "27 Credits"), PRICE_HTML.replace("/ sec", "/ minute"),
    PRICE_HTML.replace("seedance-2.0-fast", "unknown-model")])
def test_missing_ambiguous_or_changed_units_fail_closed(html):
    with pytest.raises(ConflictError):
        parse_rates(html)
