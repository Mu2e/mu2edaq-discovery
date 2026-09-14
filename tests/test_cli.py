import json

import pytest

from mu2edaq_discovery import cli, protocol


RECORD = {
    "id": "service-1",
    "name": "Test VNC",
    "app": "vnc",
    "host": "daq01.example.test",
    "port": 5901,
    "started": "2026-07-22T00:00:00Z",
}


def test_main_passes_options_filters_and_writes_json(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, "discover", lambda **kwargs: calls.append(kwargs) or [RECORD])

    assert cli.main([
        "--json", "--filter", "app=vnc", "--filter", "name=Test *",
        "--timeout", "1.5", "--retries", "3", "--group", "239.1.2.3",
        "--port", "30001", "--interface", "127.0.0.1",
    ]) == 0

    assert calls == [{
        "filter": {"app": "vnc", "name": "Test *"},
        "timeout": 1.5,
        "retries": 3,
        "group": "239.1.2.3",
        "port": 30001,
        "interface": "127.0.0.1",
        "broadcast": [protocol.BROADCAST],          # on by default
    }]
    assert json.loads(capsys.readouterr().out) == [RECORD]


# -- broadcast option precedence --------------------------------------------

def _broadcast_passed(monkeypatch, argv, env=None, cfg=None):
    captured = []
    monkeypatch.setattr(cli, "discover", lambda **kwargs: captured.append(kwargs) or [])
    monkeypatch.setattr(cli, "_load_config", lambda _path: cfg or {})
    monkeypatch.delenv("MU2EDAQ_DISCOVERY_BROADCAST", raising=False)
    if env is not None:
        monkeypatch.setenv("MU2EDAQ_DISCOVERY_BROADCAST", env)
    assert cli.main(["--json", "--config", "x.yaml", *argv]) == 0
    return captured[0]["broadcast"]


def test_no_broadcast_flag_gives_multicast_only(monkeypatch):
    assert _broadcast_passed(monkeypatch, ["--no-broadcast"]) == []


def test_broadcast_flag_is_repeatable_and_replaces_the_default(monkeypatch):
    assert _broadcast_passed(monkeypatch,
                             ["--broadcast", "131.225.245.255", "--broadcast", "10.226.9.255"]) \
        == ["131.225.245.255", "10.226.9.255"]


def test_broadcast_environment_and_config_precedence(monkeypatch):
    assert _broadcast_passed(monkeypatch, [], env="off") == []
    assert _broadcast_passed(monkeypatch, [], env="131.225.245.255, 10.226.9.255") \
        == ["131.225.245.255", "10.226.9.255"]
    assert _broadcast_passed(monkeypatch, [], cfg={"broadcast": False}) == []
    assert _broadcast_passed(monkeypatch, [], cfg={"broadcast": ["10.0.0.255"]}) == ["10.0.0.255"]
    # Environment beats config; command line beats both.
    assert _broadcast_passed(monkeypatch, [], env="off", cfg={"broadcast": ["10.0.0.255"]}) == []
    assert _broadcast_passed(monkeypatch, ["--broadcast", "1.2.3.255"], env="off") == ["1.2.3.255"]


@pytest.mark.parametrize("value, expected", [
    (None, [protocol.BROADCAST]),
    (True, [protocol.BROADCAST]),
    (False, []),
    ("off", []), ("none", []), ("", []),
    ("on", [protocol.BROADCAST]), ("default", [protocol.BROADCAST]),
    ("1.2.3.255", ["1.2.3.255"]),
    ("1.2.3.255,4.5.6.255", ["1.2.3.255", "4.5.6.255"]),
    (["1.2.3.255", " 4.5.6.255 "], ["1.2.3.255", "4.5.6.255"]),
])
def test_parse_broadcast_setting(value, expected):
    from mu2edaq_discovery import parse_broadcast_setting
    assert parse_broadcast_setting(value) == expected


def test_parse_broadcast_setting_rejects_nonsense():
    from mu2edaq_discovery import parse_broadcast_setting
    with pytest.raises(ValueError):
        parse_broadcast_setting(42)


def test_command_line_options_override_environment_and_config(monkeypatch):
    captured = []
    monkeypatch.setattr(cli, "_load_config", lambda _path: {
        "group": "239.1.1.1", "port": 10001, "timeout": 7.0,
    })
    monkeypatch.setenv("MU2EDAQ_DISCOVERY_GROUP", "239.1.1.2")
    monkeypatch.setenv("MU2EDAQ_DISCOVERY_PORT", "10002")
    monkeypatch.setenv("MU2EDAQ_DISCOVERY_TIMEOUT", "8.0")
    monkeypatch.setattr(cli, "discover", lambda **kwargs: captured.append(kwargs) or [])

    assert cli.main([
        "--json", "--config", "settings.yaml", "--group", "239.1.1.3",
        "--port", "10003", "--timeout", "9.0",
    ]) == 0

    assert captured[0]["group"] == "239.1.1.3"
    assert captured[0]["port"] == 10003
    assert captured[0]["timeout"] == 9.0


def test_main_prints_empty_table_message(monkeypatch, capsys):
    monkeypatch.setattr(cli, "discover", lambda **_kwargs: [])

    assert cli.main([]) == 0
    assert capsys.readouterr().out == "No services found.\n"


def test_invalid_filter_syntax_reports_a_cli_error():
    with pytest.raises(SystemExit, match="--filter takes key=glob"):
        cli._parse_filter(["app"])


def test_main_converts_protocol_errors_to_cli_errors(monkeypatch):
    def fail(**_kwargs):
        raise protocol.ProtocolError("bad query")

    monkeypatch.setattr(cli, "discover", fail)
    with pytest.raises(SystemExit, match="error: bad query"):
        cli.main(["--json"])
