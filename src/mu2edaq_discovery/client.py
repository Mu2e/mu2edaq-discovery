"""Discovery client: send a DISCOVER query and collect ANNOUNCE replies.

The query goes out two ways at once, and replies from both are merged by the
responder's stable ``id``:

* **multicast** to the group, the original transport; and
* **broadcast** to the local subnet (``255.255.255.255`` by default), because
  on a network whose switches run IGMP snooping without a querier the
  multicast is forwarded only within the switch the client sits on.  That is
  the case on the Mu2e DAQ network: every node is on one /24, yet a multicast
  scan from one node finds only the nodes on its own switch.  Broadcast is not
  subject to snooping and floods the whole VLAN.

Broadcast does not cross a router, so it adds nothing off the subnet; there,
multicast routing or a unicast probe of known hosts is still needed.  Every
responder listens on ``0.0.0.0:PORT`` and so receives both forms without
change.
"""

import socket
import time

from . import protocol

_OFF = ("", "off", "no", "false", "none", "0")
_ON = ("on", "yes", "true", "1", "default")


def parse_broadcast_setting(value, default=(protocol.BROADCAST,)):
    """Normalise a ``broadcast`` option to a list of destination addresses.

    Accepts ``None`` (the default), a bool, a list/tuple of addresses, or a
    string -- ``"off"``/``"no"``/``"false"``/``"none"`` for none,
    ``"on"``/``"yes"``/``"true"``/``"default"`` for the default, or addresses
    separated by commas or whitespace.  This is the one place the command
    line, the environment, the config file and the API agree on the spelling.
    """
    if value is None:
        return list(default)
    if isinstance(value, bool):
        return list(default) if value else []
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in _OFF:
            return []
        if text.lower() in _ON:
            return list(default)
        return [a.strip() for a in text.replace(",", " ").split() if a.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(a).strip() for a in value if str(a).strip()]
    raise ValueError("broadcast must be a bool, a string or a list of addresses, "
                     "not %r" % (value,))


def discover(filter=None, timeout=2.0, retries=2, group=protocol.GROUP,
             port=protocol.PORT, interface=None, broadcast=True):
    """Send a DISCOVER query and return the list of ANNOUNCE dicts.

    The query is multicast to *group* and, unless *broadcast* is false or
    empty, also broadcast to each address it names (``True`` means the
    limited broadcast ``255.255.255.255``; a list means those addresses, e.g.
    a subnet's own broadcast address).  It is sent `retries` times, spread
    across the *timeout* window; responders are deduplicated by their stable
    ``id``, so a host reached both ways counts once.  Replies are collected
    until *timeout* seconds have elapsed in total.

    *interface* is the local IP to send from, for multi-homed hosts; it also
    decides which subnet the broadcast leaves on.
    """
    broadcast_addrs = parse_broadcast_setting(broadcast)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    if broadcast_addrs:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if interface:
        sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
            socket.inet_aton(interface),
        )
        # Binding to the interface address makes the broadcast leave on that
        # interface too, not just the multicast.
        sock.bind((interface, 0))
    else:
        sock.bind(("", 0))

    query = protocol.build_query(filter=filter)
    qid = query["qid"]
    payload = protocol.encode(query)

    def send_all():
        sock.sendto(payload, (group, port))
        for addr in broadcast_addrs:
            try:
                sock.sendto(payload, (addr, port))
            except OSError:
                # A broadcast address that is not valid from this host (an
                # interface without one, a sandbox) must not spoil the
                # multicast leg; the multicast send above raised if the
                # socket itself is broken.
                pass

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
                send_all()
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
