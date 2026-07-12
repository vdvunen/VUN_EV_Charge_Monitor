"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Gedeelde helpers voor providerimplementaties — voorkomt dubbele logica
tussen ndw.py, tomtom.py en open_charge_map.py (opdracht §42).
"""

from __future__ import annotations

from ..models import ChargeLocation, ConnectorType

# Tolerante, best-effort mapping van providerspecifieke connectortypereeksen
# naar het interne model. Onbekende waarden vallen veilig terug op UNKNOWN
# in plaats van te crashen (providerresponses mogen nooit worden aangenomen
# exact te zijn, zie opdracht §42).
_CONNECTOR_TYPE_KEYWORDS: dict[str, ConnectorType] = {
    "t2combo": ConnectorType.CCS,
    "ccs": ConnectorType.CCS,
    "combo": ConnectorType.CCS,
    "t2": ConnectorType.TYPE_2,
    "type2": ConnectorType.TYPE_2,
    "type_2": ConnectorType.TYPE_2,
    "mennekes": ConnectorType.TYPE_2,
    "chademo": ConnectorType.CHADEMO,
    "t1": ConnectorType.TYPE_1,
    "type1": ConnectorType.TYPE_1,
    "type_1": ConnectorType.TYPE_1,
    "j1772": ConnectorType.TYPE_1,
    "domestic": ConnectorType.DOMESTIC,
    "schuko": ConnectorType.DOMESTIC,
    "wall": ConnectorType.DOMESTIC,
}


def map_connector_type(raw: str | None) -> ConnectorType:
    """Vertaal een providerspecifieke connectortypestring naar ConnectorType.

    Let op volgorde: "ccs"/"combo" wordt vóór de generieke "t2"-check
    gematcht, zodat "IEC_62196_T2_COMBO" (CCS) niet abusievelijk als kaal
    Type 2 wordt herkend.
    """
    if not raw:
        return ConnectorType.UNKNOWN
    lowered = raw.strip().lower().replace(" ", "").replace("-", "")
    for keyword in ("t2combo", "ccs", "combo"):
        if keyword in lowered:
            return ConnectorType.CCS
    for keyword, connector_type in _CONNECTOR_TYPE_KEYWORDS.items():
        if keyword in lowered:
            return connector_type
    return ConnectorType.UNKNOWN


def navigation_url(latitude: float, longitude: float) -> str:
    """Genereer een externe navigatielink (opdracht §4 staat dit expliciet toe)."""
    return f"https://www.google.com/maps/dir/?api=1&destination={latitude},{longitude}"


def passes_filters(
    location: ChargeLocation,
    *,
    radius_m: float,
    connector_types: frozenset[ConnectorType] | None,
    min_power_kw: float,
) -> bool:
    """Gedeelde na-normalisatie-filterstap (radius/connector/vermogen), zie opdracht §14."""
    if location.distance_m is not None and location.distance_m > radius_m:
        return False
    if connector_types and not (location.connector_types & connector_types):
        return False
    return not (min_power_kw and (location.max_power_kw or 0) < min_power_kw)
