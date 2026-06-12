"""mu2edaq-discovery: UDP multicast service discovery for Mu2e DAQ applications."""

from .client import discover
from .responder import Responder
from . import protocol

__version__ = "1.0.0"
__all__ = ["Responder", "discover", "protocol"]
