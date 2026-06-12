"""Discovery client: send a DISCOVER query and collect ANNOUNCE replies."""

import socket
import time

from . import protocol


def discover(filter=None, timeout=2.0, retries=2, group=protocol.GROUP,
             port=protocol.PORT, interface=None):
    """Multicast a DISCOVER query and return the list of ANNOUNCE dicts.

    The query is sent `retries` times (responders are deduplicated by
    their stable `id`), and replies are collected until `timeout`
    seconds have elapsed in total.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    if interface:
        sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
            socket.inet_aton(interface),
        )
    sock.bind(("", 0))

    query = protocol.build_query(filter=filter)
    qid = query["qid"]
    payload = protocol.encode(query)

    found = {}
    deadline = time.monotonic() + timeout
    resend_at = 0.0
    sends_left = max(1, retries)
    try:
        while True:
            now = time.monotonic()
            if now >= deadline:
                break
            if sends_left > 0 and now >= resend_at:
                sock.sendto(payload, (group, port))
                sends_left -= 1
                # Spread the resends across the timeout window.
                resend_at = now + timeout / max(1, retries)
            sock.settimeout(min(deadline, resend_at if sends_left else deadline) - now)
            try:
                data, _addr = sock.recvfrom(protocol.MAX_DATAGRAM + 1)
            except socket.timeout:
                continue
            try:
                msg = protocol.decode(data)
            except protocol.ProtocolError:
                continue
            if msg["type"] != "ANNOUNCE":
                continue
            # Accept replies to our query and unsolicited announces.
            if "qid" in msg and msg["qid"] != qid:
                continue
            if not protocol.matches_filter(msg, filter):
                continue
            found[msg["id"]] = msg
    finally:
        sock.close()
    return sorted(found.values(), key=lambda m: (m.get("host", ""), m.get("port", 0)))
