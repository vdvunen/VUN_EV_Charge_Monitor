"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Generieke async API-client met timeouts, retries, exponential back-off en
HTTP 429/Retry-After-afhandeling. Providerneutraal — providers/*.py en
distance.py bouwen hierop verder en zijn zelf verantwoordelijk voor
normalisatie naar het interne datamodel.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class ApiError(Exception):
    """Basisklasse voor alle API-clientfouten."""


class ApiAuthError(ApiError):
    """HTTP 401/403."""


class ApiRateLimitedError(ApiError):
    """HTTP 429."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ApiConnectionError(ApiError):
    """Netwerkfout, timeout, of tijdelijke serverfout (5xx) na uitputten van retries."""


class ApiResponseError(ApiError):
    """Lege of malformed response."""


def _safe_exc_text(err: Exception) -> str:
    """Beschrijf een externe exceptie zonder de originele boodschap over te nemen.

    Sommige aiohttp-excepties (bv. ``ContentTypeError``) embedden de volledige
    aangevraagde URL — inclusief querystring — in hun ``__str__``. Providers
    die een API-key als queryparameter versturen (zoals TomTom) zouden die
    key dan ongewild in HA-logs kunnen laten belanden via onze eigen
    foutmeldingen (opdracht §22: "API-keys nooit loggen"). Daarom wordt hier
    uitsluitend het excepties-type gebruikt, nooit ``str(err)``.
    """
    return type(err).__name__


class ApiClient:
    """Herbruikbare async HTTP-client gebouwd op de gedeelde HA aiohttp-sessie."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        connect_timeout_s: float = 5,
        total_timeout_s: float = 20,
        max_retries: int = 3,
        backoff_base_s: float = 1.0,
    ) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(
            total=total_timeout_s, connect=connect_timeout_s
        )
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        self.retry_count = 0
        """Aantal retries tijdens de laatst uitgevoerde call (voor diagnostics)."""

    async def async_get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Voer een GET-request uit en retourneer de gedecodeerde JSON-body."""
        return await self._async_request_json("GET", url, params=params, headers=headers)

    async def async_post_json(
        self,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Voer een POST-request uit met een JSON-body en retourneer de gedecodeerde respons."""
        return await self._async_request_json("POST", url, json_body=json_body, headers=headers)

    async def _async_request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Voer een request uit en retourneer de gedecodeerde JSON-body.

        Retryt op timeouts, connectiefouten en HTTP 5xx met exponentiële
        back-off (begrensd tot ``max_retries`` pogingen). HTTP 429 wordt
        gerespecteerd via ``Retry-After`` maar levert geen agressieve
        retrylus op — na de laatste toegestane poging wordt
        ``ApiRateLimitedError`` opgeworpen aan de aanroeper.
        """
        self.retry_count = 0
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            self.retry_count = attempt
            try:
                async with self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=self._timeout,
                ) as response:
                    if response.status == 401 or response.status == 403:
                        raise ApiAuthError(
                            f"Authenticatie geweigerd (HTTP {response.status})"
                        )

                    if response.status == 429:
                        retry_after = _parse_retry_after(
                            response.headers.get("Retry-After")
                        )
                        if attempt >= self._max_retries:
                            raise ApiRateLimitedError(
                                "Rate limit bereikt (HTTP 429)", retry_after
                            )
                        wait_s = retry_after if retry_after is not None else (
                            self._backoff_base_s * (2**attempt)
                        )
                        _LOGGER.debug(
                            "HTTP 429 ontvangen, wacht %.1fs voor retry %d/%d",
                            wait_s,
                            attempt + 1,
                            self._max_retries,
                        )
                        await asyncio.sleep(wait_s)
                        continue

                    if response.status >= 500:
                        if attempt >= self._max_retries:
                            raise ApiConnectionError(
                                f"Server blijft fouten geven (HTTP {response.status}) "
                                f"na {self._max_retries} pogingen"
                            )
                        wait_s = self._backoff_base_s * (2**attempt)
                        _LOGGER.debug(
                            "HTTP %s ontvangen, retry %d/%d over %.1fs",
                            response.status,
                            attempt + 1,
                            self._max_retries,
                            wait_s,
                        )
                        await asyncio.sleep(wait_s)
                        continue

                    if response.status >= 400:
                        raise ApiResponseError(
                            f"Onverwachte clientfout (HTTP {response.status})"
                        )

                    try:
                        return await response.json(content_type=None)
                    except (aiohttp.ContentTypeError, ValueError) as err:
                        raise ApiResponseError(
                            f"Response is geen geldige JSON ({_safe_exc_text(err)})"
                        ) from err

            except (ApiAuthError, ApiResponseError, ApiRateLimitedError):
                raise
            except TimeoutError as err:
                last_error = err
                if attempt >= self._max_retries:
                    raise ApiConnectionError("Timeout na alle retries") from err
                wait_s = self._backoff_base_s * (2**attempt)
                _LOGGER.debug(
                    "Timeout, retry %d/%d over %.1fs", attempt + 1, self._max_retries, wait_s
                )
                await asyncio.sleep(wait_s)
            except aiohttp.ClientError as err:
                last_error = err
                if attempt >= self._max_retries:
                    raise ApiConnectionError(
                        f"Verbindingsfout na alle retries ({_safe_exc_text(err)})"
                    ) from err
                wait_s = self._backoff_base_s * (2**attempt)
                _LOGGER.debug(
                    "Verbindingsfout, retry %d/%d over %.1fs",
                    attempt + 1,
                    self._max_retries,
                    wait_s,
                )
                await asyncio.sleep(wait_s)

        # Onbereikbaar in de praktijk (elke tak hierboven raise't of continue't),
        # maar voorkomt een impliciete None-return bij statische analyse.
        detail = _safe_exc_text(last_error) if last_error else "onbekend"
        raise ApiConnectionError(f"Onbekende fout ({detail})")


def _parse_retry_after(value: str | None) -> float | None:
    """Parse de Retry-After header (seconden of HTTP-date, alleen seconden ondersteund)."""
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
