"""Discovery responder: a daemon thread applications embed to answer
DISCOVER queries and optionally multicast periodic announcements.

Usage:
    from mu2edaq_discovery import Responder
    r = Responder(name="My App", app="dashboard", port=5001)
    r.start()
    ...
    r.stop()
"""

import random
import socket
import struct
import threading
import time
import uuid

from . import protocol


class Responder(threading.Thread):
    """Answers DISCOVER queries with a unicast ANNOUNCE.

    Joins the multicast group on a dedicated socket. Replies are
    delayed by a random 0-250 ms jitter to avoid reply storms when
    many responders share a network. If announce_interval > 0, an
    unsolicited ANNOUNCE is also multicast to the group periodically.
    """

    JITTER_MAX = 0.250

    def __init__(self, name, app, port, scheme=None, version=None, meta=None,
                 host=None, group=protocol.GROUP, listen_port=protocol.PORT,
                 announce_interval=0, bind_interface=None):
        super().__init__(daemon=True, name="mu2edaq-discovery-responder")
        self.instance_id = str(uuid.uuid4())
        self._announce_kwargs = dict(
            name=name, app=app, port=port, scheme=scheme,
            version=version, meta=meta, host=host,
        )
        self.group = group
        self.listen_port = listen_port
        self.announce_interval = announce_interval
        self.bind_interface = bind_interface or "0.0.0.0"
        self._stop_event = threading.Event()
        self._sock = None

    # -- lifecycle ---------------------------------------------------------

    def stop(self, timeout=2.0):
        """Signal the thread to exit and wait for it."""
        self._stop_event.set()
        # Unblock the recvfrom() by poking our own listen port.
        try:
            poke = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            poke.sendto(b"", ("127.0.0.1", self.listen_port))
            poke.close()
        except OSError:
            pass
        self.join(timeout=timeout)

    # -- internals ---------------------------------------------------------

    def _open_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        sock.bind(("", self.listen_port))
        mreq = struct.pack(
            "4s4s",
            socket.inet_aton(self.group),
            socket.inet_aton(self.bind_interface),
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(0.5)
        return sock

    def _announce(self, qid=None):
        return protocol.build_announce(
            instance_id=self.instance_id, qid=qid, **self._announce_kwargs
        )

    def run(self):
        self._sock = self._open_socket()
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
        send_sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
            socket.inet_aton(self.bind_interface),
        )
        next_announce = (
            time.monotonic() + self.announce_interval
            if self.announce_interval > 0 else None
        )
        try:
            while not self._stop_event.is_set():
                if next_announce is not None and time.monotonic() >= next_announce:
                    try:
                        send_sock.sendto(
                            protocol.encode(self._announce()),
                            (self.group, self.listen_port),
                        )
                    except OSError:
                        pass
                    next_announce = time.monotonic() + self.announce_interval
                try:
                    data, addr = self._sock.recvfrom(protocol.MAX_DATAGRAM + 1)
                except socket.timeout:
                    continue
                if self._stop_event.is_set():
                    break
                try:
                    msg = protocol.decode(data)
                except protocol.ProtocolError:
                    continue
                if msg["type"] != "DISCOVER":
                    continue
                if not protocol.matches_filter(self._announce(), msg.get("filter")):
                    continue
                time.sleep(random.uniform(0, self.JITTER_MAX))
                reply = protocol.encode(self._announce(qid=msg.get("qid")))
                try:
                    send_sock.sendto(reply, addr)
                except OSError:
                    pass
        finally:
            send_sock.close()
            self._sock.close()
