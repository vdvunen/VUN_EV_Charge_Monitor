"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Intern, provideronafhankelijk datamodel voor laadlocaties.

Zie FASE1-ONDERZOEK-EN-ARCHITECTUUR.md §4 en opdracht §9/§10 voor de
onderliggende ontwerpbeslissingen (OCPI Location -> EVSE -> Connector
hierarchie, statusnormalisatie).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ConnectorType(StrEnum):
    """Genormaliseerde connectortypen."""

    TYPE_2 = "type_2"
    CCS = "ccs"
    CHADEMO = "chademo"
    TYPE_1 = "type_1"
    DOMESTIC = "domestic"
    UNKNOWN = "unknown"


class ChargePointStatus(StrEnum):
    """Genormaliseerde EVSE-status (opdracht §10, gebaseerd op OCPI Status-enum)."""

    AVAILABLE = "available"
    OCCUPIED = "occupied"
    CHARGING = "charging"
    RESERVED = "reserved"
    OUT_OF_ORDER = "out_of_order"
    INOPERATIVE = "inoperative"
    UNKNOWN = "unknown"
    PLANNED = "planned"
    REMOVED = "removed"

    @property
    def is_available(self) -> bool:
        return self is ChargePointStatus.AVAILABLE


class DataQuality(StrEnum):
    """Onderscheid tussen actuele en statische brondata (opdracht §7.3/§10)."""

    REALTIME = "realtime"
    STATIC = "static"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Connector:
    """Eén fysieke aansluiting (stekkertype) op een EVSE. Metadata only —
    telt niet los mee voor beschikbaarheid, zie ChargeLocation-docstring."""

    connector_type: ConnectorType
    max_power_kw: float | None = None


@dataclass(frozen=True, slots=True)
class Evse:
    """Eén laadpunt (Electric Vehicle Supply Equipment).

    Connectoren op dezelfde EVSE kunnen nooit gelijktijdig gebruikt worden
    (bevestigd in OCPI mod_locations spec, zie FASE1-onderzoek §1.4). De EVSE
    is daarom de telbare eenheid voor beschikbaarheid, niet de Connector.
    """

    evse_id: str
    status: ChargePointStatus
    connectors: tuple[Connector, ...] = field(default_factory=tuple)

    @property
    def is_available(self) -> bool:
        return self.status.is_available

    @property
    def max_power_kw(self) -> float | None:
        powers = [c.max_power_kw for c in self.connectors if c.max_power_kw is not None]
        return max(powers) if powers else None

    @property
    def connector_types(self) -> frozenset[ConnectorType]:
        return frozenset(c.connector_type for c in self.connectors)


@dataclass(frozen=True, slots=True)
class ChargeLocation:
    """Eén laadlocatie (OCPI Location) met één of meer EVSE's.

    Telsemantiek (opdracht §10):
    - "beschikbare locatie": ``is_available`` == True, d.w.z. minimaal één
      EVSE met status AVAILABLE.
    - "beschikbare EVSE" / "beschikbare aansluiting": deze integration
      gebruikt beide termen voor hetzelfde begrip — het aantal EVSE's met
      status AVAILABLE. Er wordt bewust NIET per Connector geteld, omdat
      connectoren op dezelfde EVSE niet gelijktijdig bruikbaar zijn (zou
      dubbeltelling opleveren).
    - "totaal aantal aansluitingen" (``total_connectors``): het aantal
      fysieke Connector-objecten (stekkers), puur informatief voor het
      tonen van connectordiversiteit — niet gebruikt voor
      beschikbaarheidsberekeningen.
    """

    provider: str
    provider_location_id: str
    external_id: str | None
    name: str
    latitude: float
    longitude: float
    address: str | None
    postal_code: str | None
    city: str | None
    country: str | None
    operator: str | None
    distance_m: float | None
    navigation_url: str
    evses: tuple[Evse, ...]
    realtime_data_available: bool
    provider_status_raw: str | None
    last_status_update: datetime | None
    last_successful_update: datetime | None
    source_quality: DataQuality
    confidence_score: float | None = None

    @property
    def total_evses(self) -> int:
        return len(self.evses)

    @property
    def available_evses(self) -> int:
        return sum(1 for e in self.evses if e.status is ChargePointStatus.AVAILABLE)

    @property
    def occupied_evses(self) -> int:
        return sum(
            1
            for e in self.evses
            if e.status in (ChargePointStatus.OCCUPIED, ChargePointStatus.CHARGING)
        )

    @property
    def reserved_evses(self) -> int:
        return sum(1 for e in self.evses if e.status is ChargePointStatus.RESERVED)

    @property
    def out_of_order_evses(self) -> int:
        return sum(
            1
            for e in self.evses
            if e.status
            in (
                ChargePointStatus.OUT_OF_ORDER,
                ChargePointStatus.INOPERATIVE,
                ChargePointStatus.REMOVED,
            )
        )

    @property
    def unknown_evses(self) -> int:
        return sum(
            1
            for e in self.evses
            if e.status in (ChargePointStatus.UNKNOWN, ChargePointStatus.PLANNED)
        )

    @property
    def total_connectors(self) -> int:
        return sum(len(e.connectors) for e in self.evses)

    @property
    def available_connectors(self) -> int:
        """Alias voor available_evses — zie klassedocstring (voorkomt dubbeltelling)."""
        return self.available_evses

    @property
    def connector_types(self) -> frozenset[ConnectorType]:
        types: set[ConnectorType] = set()
        for evse in self.evses:
            types |= evse.connector_types
        return frozenset(types)

    @property
    def max_power_kw(self) -> float | None:
        powers = [e.max_power_kw for e in self.evses if e.max_power_kw is not None]
        return max(powers) if powers else None

    @property
    def is_available(self) -> bool:
        return self.available_evses > 0


@dataclass(frozen=True, slots=True)
class ProviderFetchResult:
    """Resultaat van één providerbevraging, vóór filtering/sortering door de coordinator."""

    locations: tuple[ChargeLocation, ...]
    source_name: str
    fetched_at: datetime
    realtime_available: bool
