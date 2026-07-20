import json

import pytest

from ccost.cli import _load_pricing, build_parser


@pytest.mark.parametrize("flag", ["--days", "--limit"])
def test_positive_integer_options_reject_zero_and_negative(flag):
    parser = build_parser()
    for value in ("0", "-1"):
        with pytest.raises(SystemExit):
            parser.parse_args([flag, value])


@pytest.mark.parametrize("data", [[], {"fable": {"input": -1, "output": 50}}, {"fable": {"input": 10}}])
def test_pricing_file_rejects_invalid_shapes(tmp_path, data):
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(data))
    with pytest.raises(SystemExit, match="invalid pricing file"):
        _load_pricing(str(path))


def test_pricing_file_accepts_nonnegative_numeric_rates(tmp_path):
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps({"fable": {"input": 10, "output": 50.0}}))
    assert _load_pricing(str(path)) == {"fable": {"input": 10, "output": 50.0}}
