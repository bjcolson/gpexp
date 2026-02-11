from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Message:
    """Base class for messages sent to a terminal."""


@dataclass
class Result:
    """Base class for typed results from a terminal operation."""
