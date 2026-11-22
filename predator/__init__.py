"""Biblioteca de protocolo, telemetria e controle do drone Predator."""

from .link import Drone, Telemetry
from .movimento import MovimentoConfig

__all__ = ["Drone", "Telemetry", "VideoStream", "MovimentoConfig"]
__version__ = "0.1.0"


def __getattr__(name):
    if name == "VideoStream":
        from .video import VideoStream
        return VideoStream
    raise AttributeError(name)
