"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Abstracte providerbasis. Iedere concrete provider normaliseert zijn eigen
API-respons naar het interne datamodel (models.py) en mag nooit ruwe
providerdata lekken naar coordinator/entities.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import ConnectorType, ProviderFetchResult


class ProviderError(Exception):
    """Basisklasse voor alle providerfouten."""


class ProviderAuthError(ProviderError):
    """API-key ontbreekt of is ongeldig/verlopen (HTTP 401/403)."""


class ProviderConnectionError(ProviderError):
    """Netwerkfout, timeout, of tijdelijke serverfout (5xx) na uitputten van retries."""


class ProviderRateLimitedError(ProviderError):
    """HTTP 429 ontvangen; retry_after in seconden indien opgegeven door de bron."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderResponseError(ProviderError):
    """Response is leeg, malformed, of mist verplichte velden."""


class ChargeLocationProvider(ABC):
    """Contract waaraan iedere providerimplementatie moet voldoen."""

    name: str

    @abstractmethod
    async def async_get_locations(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_m: float,
        max_results: int,
        connector_types: frozenset[ConnectorType] | None = None,
        min_power_kw: float = 0.0,
    ) -> ProviderFetchResult:
        """Haal genormaliseerde laadlocaties op binnen de opgegeven radius.

        Implementaties moeten:
        - server-side geografisch filteren waar de bron dit ondersteunt;
        - ongeldige records negeren i.p.v. de hele call te laten falen;
        - ProviderAuthError/ProviderRateLimitedError/ProviderConnectionError/
          ProviderResponseError gebruiken voor foutafhandeling door de
          coordinator (nooit provider-specifieke excepties lekken).
        """
