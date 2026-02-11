from __future__ import annotations

import logging
from typing import Callable

from gpexp.core.base.agent import Agent
from gpexp.core.base.message import Message, Result

lg = logging.getLogger(__name__)


def handles(message_cls: type[Message]) -> Callable:
    """Decorator that registers a method as handler for a message type."""

    def decorator(method: Callable) -> Callable:
        method._handles_message = message_cls
        return method

    return decorator


class Terminal:
    """Base terminal that drives a scenario through an Agent.

    The app layer sends Message objects via send() and receives Result objects.
    Subclasses register handlers with the @handles decorator. The send()
    method dispatches to the appropriate handler based on message type.
    """

    _handlers: dict[type[Message], str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls._handlers = {}
        for base in reversed(cls.__mro__):
            if hasattr(base, "_handlers"):
                cls._handlers.update(base._handlers)
        for name in vars(cls):
            method = getattr(cls, name)
            if callable(method) and hasattr(method, "_handles_message"):
                cls._handlers[method._handles_message] = name

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    def connect(self) -> None:
        """Connect to a card via the agent."""
        self._agent.connect()

    def disconnect(self) -> None:
        """Disconnect from the card via the agent."""
        self._agent.disconnect()

    def send(self, message: Message) -> Result:
        """Dispatch a message to the registered handler."""
        handler_name = self._handlers.get(type(message))
        if handler_name is None:
            raise ValueError(f"unsupported message: {message}")
        return getattr(self, handler_name)(message)

    @property
    def supported_messages(self) -> list[type[Message]]:
        """Return the message types this terminal can handle."""
        return list(self._handlers.keys())

    def on_error(self, error: Exception) -> None:
        """Handle an error during scenario execution."""
        lg.error("terminal error: %s", error)
