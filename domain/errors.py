"""Shared error types for the forwarding pipeline."""

from __future__ import annotations


class ForwarderError(RuntimeError):
    """Base class for every recoverable error raised by the forwarder."""


class ConfigurationError(ForwarderError):
    """Raised when the environment configuration is missing or invalid."""


class EventSourceError(ForwarderError):
    """Raised when events cannot be retrieved from the event source."""


class DeliveryError(ForwarderError):
    """Raised when an event cannot be delivered to the destination."""
