"""Template card information data model.

Extend CardInfo with fields specific to your card. Runner commands
store collected data here (e.g. ``runner._info.version = ...``).
"""

from __future__ import annotations

from dataclasses import dataclass

from gpexp.app.generic.cardinfo import CardInfo


@dataclass
class TemplateCardInfo(CardInfo):
    """Card information for the template card.

    Inherits uid, atr, fci from CardInfo. Add your card-specific
    fields below.
    """

    version: bytes = b""
