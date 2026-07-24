"""End-to-end Responder <-> discover() test over loopback multicast.

Skipped automatically if the environment cannot do multicast on
loopback (some CI sandboxes); run locally to validate the full path.
"""

import socket
import struct
import time

import pytest

from mu2edaq_discovery import Responder, discover, protocol

LOOPBACK = "127.0.0.1"
# Use a non-default port so the tests never collide with a real deployment.
TEST_PORT = 28998


def _multicast_loopback_available():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", TEST_PORT))
        mreq = struct.pack("4s4s", socket.inet_aton(protocol.GROUP),
                           socket.inet_aton(LOOPBACK))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _multicast_loopback_available(),
    reason="multicast on loopback not available in this environment",
)


@pytest.fixture
def responder():
    r = Responder(
        name="test-vnc", app="vnc", port=5901,
        meta={"display": ":1", "geometry": "1920x1080"},
        listen_port=TEST_PORT, bind_interface=LOOPBACK,
    )
    r.start()
    yield r
    r.stop()


def _scan(**kwargs):
    kwargs.setdefault("port", TEST_PORT)
    kwargs.setdefault("interface", LOOPBACK)
    kwargs.setdefault("timeout", 1.5)
    return discover(**kwargs)


def test_discover_finds_responder(responder):
    results = _scan()
    assert any(r["id"] == responder.instance_id for r in results)
    mine = next(r for r in results if r["id"] == responder.instance_id)
    assert mine["name"] == "test-vnc"
    assert mine["app"] == "vnc"
    assert mine["port"] == 5901
    assert mine["meta"]["display"] == ":1"


def test_discover_filter_match(responder):
    results = _scan(filter={"app": "vnc"})
    assert any(r["id"] == responder.instance_id for r in results)


def test_discover_filter_no_match(responder):
    results = _scan(filter={"app": "dashboard"})
    assert not any(r["id"] == responder.instance_id for r in results)


def test_dedup_across_retries(responder):
    results = _scan(retries=3, timeout=2.0)
    ids = [r["id"] for r in results if r["id"] == responder.instance_id]
    assert len(ids) == 1


def test_responder_stop_is_clean():
    r = Responder(name="stoppable", app="test", port=1234,
                  listen_port=TEST_PORT, bind_interface=LOOPBACK)
    r.start()
    r.stop()
    assert not r.is_alive()


def test_responder_ignores_malformed_filter(responder):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(
            b'{"proto":"mu2edaq-discovery/1","type":"DISCOVER",'
            b'"qid":"bad-filter","filter":[]}',
            (LOOPBACK, TEST_PORT),
        )
    finally:
        sock.close()
    time.sleep(0.1)
    assert responder.is_alive()
