"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Providerabstractie — normaliseert externe laadpuntbronnen naar het interne
datamodel (models.py). Zie FASE1-ONDERZOEK-EN-ARCHITECTUUR.md §2/§5.
"""

from __future__ import annotations

from .base import (
    ChargeLocationProvider,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimitedError,
    ProviderResponseError,
)
from .ndw import NdwProvider
from .open_charge_map import OpenChargeMapProvider
from .simulation import SimulationProvider
from .tomtom import TomTomProvider

__all__ = [
    "ChargeLocationProvider",
    "NdwProvider",
    "OpenChargeMapProvider",
    "ProviderAuthError",
    "ProviderConnectionError",
    "ProviderError",
    "ProviderRateLimitedError",
    "ProviderResponseError",
    "SimulationProvider",
    "TomTomProvider",
]
