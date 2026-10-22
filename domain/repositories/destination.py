"""Port for delivering events to a destination."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.event import Event


class Destination(ABC):
    """Sends a single event to its final destination."""

    @abstractmethod
    def send(self, event: Event) -> None:
        """Deliver ``event``.

        Implementations raise :class:`domain.errors.DeliveryError` when the
        delivery fails.
        """
