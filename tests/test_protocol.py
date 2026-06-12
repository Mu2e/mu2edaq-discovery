import pytest

from mu2edaq_discovery import protocol


def test_query_round_trip():
    q = protocol.build_query(filter={"app": "vnc"})
    decoded = protocol.decode(protocol.encode(q))
    assert decoded == q
    assert decoded["type"] == "DISCOVER"
    assert decoded["filter"] == {"app": "vnc"}


def test_query_without_filter():
    q = protocol.build_query()
    assert "filter" not in q
    assert q["proto"] == protocol.PROTO


def test_query_rejects_unknown_filter_key():
    with pytest.raises(protocol.ProtocolError):
        protocol.build_query(filter={"bogus": "*"})


def test_announce_round_trip():
    a = protocol.build_announce(
        name="VNC mu2e-dl-01 :1", app="vnc", port=5901,
        instance_id="abc-123", qid="q-1",
        host="mu2e-dl-01.fnal.gov", meta={"display": ":1"},
    )
    decoded = protocol.decode(protocol.encode(a))
    assert decoded == a
    assert decoded["port"] == 5901
    assert decoded["qid"] == "q-1"
    assert decoded["meta"]["display"] == ":1"


def test_announce_without_qid_is_unsolicited():
    a = protocol.build_announce(name="x", app="y", port=1, instance_id="i")
    assert "qid" not in a


def test_decode_rejects_garbage():
    with pytest.raises(protocol.ProtocolError):
        protocol.decode(b"\xff\xfe not json")
    with pytest.raises(protocol.ProtocolError):
        protocol.decode(b'"just a string"')
    with pytest.raises(protocol.ProtocolError):
        protocol.decode(b'{"proto": "other/9", "type": "DISCOVER"}')
    with pytest.raises(protocol.ProtocolError):
        protocol.decode(b'{"proto": "mu2edaq-discovery/1", "type": "NOPE"}')


def test_encode_rejects_oversize():
    a = protocol.build_announce(name="x", app="y", port=1, instance_id="i",
                                meta={"blob": "z" * 2000})
    with pytest.raises(protocol.ProtocolError):
        protocol.encode(a)


def test_filter_matching():
    a = protocol.build_announce(name="VNC daq-main", app="vnc", port=5901,
                                instance_id="i", host="mu2e-dl-01.fnal.gov")
    assert protocol.matches_filter(a, None)
    assert protocol.matches_filter(a, {})
    assert protocol.matches_filter(a, {"app": "vnc"})
    assert protocol.matches_filter(a, {"app": "v*"})
    assert protocol.matches_filter(a, {"host": "mu2e-dl-*"})
    assert protocol.matches_filter(a, {"name": "VNC *"})
    assert not protocol.matches_filter(a, {"app": "dashboard"})
    assert not protocol.matches_filter(a, {"host": "mu2e-mgr-*"})
    assert not protocol.matches_filter(a, {"bogus": "*"})
