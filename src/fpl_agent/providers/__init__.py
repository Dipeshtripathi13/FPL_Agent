"""Permitted, pluggable research providers."""

from fpl_agent.providers.base import EvidenceProvider, ProviderDocument
from fpl_agent.providers.brave import BraveSearchProvider

__all__ = ["BraveSearchProvider", "EvidenceProvider", "ProviderDocument"]
