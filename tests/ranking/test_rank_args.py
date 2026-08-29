import pytest

from src.pytest_regsmart.const import RANK_LEVEL
from src.pytest_regsmart.ranking.rank_args import (
    parse_hist_len,
    parse_no_rank,
    parse_replay,
    parse_rtp_level,
    parse_rtp_weights,
    parse_seed,
)


class _FakeConfig:
    def __init__(self, option, ini=None):
        self._option = option
        self._ini = ini

    def getoption(self, _name):
        return self._option

    def getini(self, _name):
        return self._ini


@pytest.mark.parametrize(
    ("option", "ini", "expected"),
    [
        pytest.param("0-1", "1-0", [0, 1], id="cli value wins over ini"),
        pytest.param(
            "1-0",
            "0.4-0.2",
            pytest.approx([0.4 / 0.6, 0.2 / 0.6]),
            id="ini used when cli has default",
        ),
        pytest.param("1-0", None, [1, 0], id="default when ini unset"),
        pytest.param("0-0", None, [0, 0], id="zero sum returns zeros"),
    ],
)
def test_parse_rtp_weights(option, ini, expected):
    config = _FakeConfig(option=option, ini=ini)

    assert parse_rtp_weights(config) == expected


@pytest.mark.parametrize(
    ("option", "ini", "expected"),
    [
        pytest.param("module", "put", "module", id="cli value wins over ini"),
        pytest.param(
            RANK_LEVEL.PUT,
            "function",
            "function",
            id="ini used when cli has default",
        ),
        pytest.param(RANK_LEVEL.PUT, "put", "put", id="default is plain str"),
    ],
)
def test_parse_rtp_level(option, ini, expected):
    result = parse_rtp_level(_FakeConfig(option=option, ini=ini))

    assert result == expected
    assert type(result) is str


@pytest.mark.parametrize(
    "from_cli",
    [
        pytest.param(True, id="cli value wins over ini"),
        pytest.param(False, id="ini uses valid file"),
    ],
)
def test_parse_replay_uses_provided_file(tmp_path, from_cli):
    ini_file = tmp_path / "ini_order.txt"
    ini_file.write_text("test_a\n")
    cli_file = tmp_path / "cli_order.txt"
    cli_file.write_text("test_a\n")

    config = _FakeConfig(
        option=str(cli_file) if from_cli else None,
        ini=str(ini_file),
    )

    expected = str(cli_file) if from_cli else str(ini_file)
    assert parse_replay(config) == expected


def test_parse_replay_default_none_when_ini_unset():
    config = _FakeConfig(option=None, ini=None)

    assert parse_replay(config) is None


def test_parse_replay_ini_missing_file_raises_usage_error(tmp_path):
    config = _FakeConfig(option=None, ini=str(tmp_path / "missing.txt"))

    with pytest.raises(pytest.UsageError, match="rank_replay"):
        parse_replay(config)


@pytest.mark.parametrize(
    ("option", "ini", "expected"),
    [
        pytest.param(40, 10, 40, id="cli value wins over ini"),
        pytest.param(50, "30", 30, id="ini used when cli has default"),
        pytest.param(50, 50, 50, id="default when ini unset"),
    ],
)
def test_parse_hist_len(option, ini, expected):
    config = _FakeConfig(option=option, ini=ini)

    assert parse_hist_len(config) == expected


@pytest.mark.parametrize(
    ("option", "ini", "expected"),
    [
        pytest.param(1234, 0, 1234, id="cli value wins over ini"),
        pytest.param(0, "42", 42, id="ini used when cli has default"),
        pytest.param(0, 0, 0, id="default when ini unset"),
    ],
)
def test_parse_seed(option, ini, expected):
    config = _FakeConfig(option=option, ini=ini)

    assert parse_seed(config) == expected


@pytest.mark.parametrize(
    ("option", "ini", "expected"),
    [
        pytest.param(False, False, False, id="default false when unset"),
        pytest.param(False, True, True, id="ini true"),
        pytest.param(True, False, True, id="cli true wins"),
    ],
)
def test_parse_no_rank(option, ini, expected):
    config = _FakeConfig(option=option, ini=ini)

    assert parse_no_rank(config) is expected


@pytest.mark.parametrize(
    ("parse_fn", "option", "ini", "match"),
    [
        pytest.param(parse_rtp_weights, "1-0", "1-3-2", "rank_weight", id="weight too many parts"),
        pytest.param(parse_rtp_weights, "1-0", "x-y", "rank_weight", id="weight non numeric parts"),
        pytest.param(parse_rtp_level, RANK_LEVEL.PUT, "class", "rank_level", id="level unknown value"),
        pytest.param(parse_hist_len, 50, "abc", "rank_hist_len", id="hist len not an integer"),
        pytest.param(parse_seed, 0, "not-a-number", "rank_seed", id="seed not an integer"),
    ],
)
def test_invalid_ini_value_raises_usage_error(parse_fn, option, ini, match):
    config = _FakeConfig(option=option, ini=ini)

    with pytest.raises(pytest.UsageError, match=match):
        parse_fn(config)
