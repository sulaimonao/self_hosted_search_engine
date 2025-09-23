"""Discovery helpers orchestrating registry-backed strategies."""

from .gather import RegistryCandidate, gather_from_registry

__all__ = ["RegistryCandidate", "gather_from_registry"]
