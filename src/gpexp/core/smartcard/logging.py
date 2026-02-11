from __future__ import annotations

import logging

TRACE = 15
PROTOCOL = 18
logging.addLevelName(TRACE, "TRACE")
logging.addLevelName(PROTOCOL, "PROTOCOL")


def _trace(self, message, *args, **kwargs):
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)


logging.Logger.trace = _trace
