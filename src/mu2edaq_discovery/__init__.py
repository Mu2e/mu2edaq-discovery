"""mu2edaq-discovery: UDP multicast and broadcast service discovery for Mu2e DAQ applications."""

from .client import discover, parse_broadcast_setting
from .responder import Responder
from . import protocol

__version__ = "1.1.0"
__all__ = ["Responder", "discover", "parse_broadcast_setting", "protocol"]
