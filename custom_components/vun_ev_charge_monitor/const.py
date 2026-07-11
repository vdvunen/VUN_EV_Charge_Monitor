"""Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl

Constants for the VUN EV Charge Monitor integration.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "vun_ev_charge_monitor"
INTEGRATION_VERSION: Final = "1.4.1"
MANUFACTURER: Final = "Vincent van Unen"
MODEL: Final = "VUN EV Charge Monitor"
CONFIGURATION_URL: Final = "https://github.com/vdvunen/VUN_EV_Charge_Monitor"

# --- Config / options keys -------------------------------------------------
CONF_ZONE: Final = "zone"
CONF_TRACKED_ENTITIES: Final = "tracked_entities"
CONF_PROVIDER: Final = "provider"
CONF_RADIUS: Final = "radius"
CONF_USE_ZONE_RADIUS: Final = "use_zone_radius"
CONF_MAX_RESULTS: Final = "max_results"
CONF_CONNECTOR_TYPES: Final = "connector_types"
CONF_MIN_POWER_KW: Final = "min_power_kw"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_MAX_DATA_AGE: Final = "max_data_age"
CONF_NOTIFICATION_TARGET: Final = "notification_target"
CONF_NOTIFICATION_COOLDOWN: Final = "notification_cooldown"
CONF_LANGUAGE: Final = "language"
CONF_NOTIFY_ON_ZONE_ENTRY: Final = "notify_on_zone_entry"
CONF_NOTIFY_ON_AVAILABILITY_CHANGE: Final = "notify_on_availability_change"
CONF_SIMULATION_MODE: Final = "simulation_mode"
CONF_OPERATOR_EXCLUDE: Final = "operator_exclude"
CONF_USE_DRIVING_DISTANCE: Final = "use_driving_distance"
CONF_ORS_API_KEY: Final = "ors_api_key"
CONF_ROUTE_DESTINATION_ZONE: Final = "route_destination_zone"
CONF_ROUTE_CORRIDOR_M: Final = "route_corridor_m"

# --- Providers ---------------------------------------------------------------
PROVIDER_NDW: Final = "ndw"
PROVIDER_TOMTOM: Final = "tomtom"
PROVIDER_OPEN_CHARGE_MAP: Final = "open_charge_map"
SUPPORTED_PROVIDERS: Final = (PROVIDER_NDW, PROVIDER_TOMTOM, PROVIDER_OPEN_CHARGE_MAP)
# TomTom en Open Charge Map vereisen een door de gebruiker aangeleverde
# API-key (opdracht §7.2/§7.3) — NDW werkt zonder key (zie FASE1-onderzoek §7).
PROVIDERS_REQUIRING_API_KEY: Final = (PROVIDER_TOMTOM, PROVIDER_OPEN_CHARGE_MAP)
DEFAULT_PROVIDER: Final = PROVIDER_NDW
# Interne providernaam voor simulatiemodus — geen "echte" provider, dus
# bewust niet opgenomen in SUPPORTED_PROVIDERS (dat is de door de gebruiker
# kiesbare databronlijst; simulatie is een aparte toggle, zie CONF_SIMULATION_MODE).
PROVIDER_SIMULATION: Final = "simulation"

# --- Defaults ------------------------------------------------------------
DEFAULT_RADIUS_M: Final = 1500
DEFAULT_MAX_RESULTS: Final = 5
DEFAULT_MIN_POWER_KW: Final = 0.0
DEFAULT_UPDATE_INTERVAL_S: Final = 300
DEFAULT_MAX_DATA_AGE_MIN: Final = 30
DEFAULT_NOTIFICATION_COOLDOWN_MIN: Final = 30
DEFAULT_LANGUAGE: Final = "nl"
DEFAULT_USE_ZONE_RADIUS: Final = False
DEFAULT_NOTIFY_ON_ZONE_ENTRY: Final = True
DEFAULT_NOTIFY_ON_AVAILABILITY_CHANGE: Final = False
DEFAULT_SIMULATION_MODE: Final = False
DEFAULT_USE_DRIVING_DISTANCE: Final = False

# --- Grenzen (configuratievalidatie) --------------------------------------
MIN_RADIUS_M: Final = 100
MAX_RADIUS_M: Final = 20000
MIN_UPDATE_INTERVAL_S: Final = 60
MAX_UPDATE_INTERVAL_S: Final = 3600
MIN_MAX_DATA_AGE_MIN: Final = 5
MAX_MAX_DATA_AGE_MIN: Final = 1440
MIN_MAX_RESULTS: Final = 1
MAX_MAX_RESULTS: Final = 20
MIN_NOTIFICATION_COOLDOWN_MIN: Final = 0
MAX_NOTIFICATION_COOLDOWN_MIN: Final = 1440

LANGUAGES: Final = ("nl", "en")

# --- Config flow foutcodes (opdracht §13) ---------------------------------
ERROR_INVALID_ZONE: Final = "invalid_zone"
ERROR_INVALID_ENTITY: Final = "invalid_entity"
ERROR_INVALID_NOTIFICATION_SERVICE: Final = "invalid_notification_service"
ERROR_INVALID_RADIUS: Final = "invalid_radius"
ERROR_INVALID_INTERVAL: Final = "invalid_interval"
ERROR_CANNOT_CONNECT: Final = "cannot_connect"
ERROR_INVALID_AUTH: Final = "invalid_auth"
ERROR_RATE_LIMITED: Final = "rate_limited"
ERROR_UNSUPPORTED_PROVIDER: Final = "unsupported_provider"
ERROR_MISSING_ROUTING_KEY: Final = "missing_routing_key"
ERROR_UNKNOWN: Final = "unknown"
# Geen aparte ERROR_NO_REALTIME_AVAILABILITY: Open Charge Map is bewust en
# permanent static-only (opdracht §7.3) — dat is normaal, verwacht gedrag
# van die provider, geen configuratiefout die de config flow moet blokkeren.
# Zichtbaarheid van "wel/geen realtime data" loopt via de
# `realtime_available`/`data_source`-sensoren en diagnostics, niet via een
# blokkerende config-flowfout.

# --- NDW DOT-NL provider ---------------------------------------------------
# Bron: FASE1-ONDERZOEK-EN-ARCHITECTUUR.md §1.1 — live bbox-GeoJSON API.
# Vaste, gecontroleerde allowlist-URL. Geen door de gebruiker vrij in te
# voeren endpoint toegestaan (voorkomt SSRF, opdracht §11/§22).
NDW_API_BASE_URL: Final = (
    "https://dotnl.ndw.nu/api/rest/geojson/dynamic-road-status/"
    "charge-point-data/v1/features"
)
NDW_CONNECT_TIMEOUT_S: Final = 5
NDW_TOTAL_TIMEOUT_S: Final = 20
NDW_MAX_RETRIES: Final = 3
NDW_BACKOFF_BASE_S: Final = 1.0
# NDW-bbox-request is begrensd tot max. 1.0 graad^2 gebied (Fase 1-onderzoek).
NDW_MAX_BBOX_DEGREES: Final = 1.0

# --- TomTom EV Search / EV Charging Stations Availability API --------------
# Bron: FASE1-ONDERZOEK-EN-ARCHITECTUUR.md §1.2. Bring-your-own-key; alleen
# actief wanneer de gebruiker zelf een geldige API-key configureert.
TOMTOM_SEARCH_URL: Final = "https://api.tomtom.com/search/2/evsearch"
TOMTOM_CONNECT_TIMEOUT_S: Final = 5
TOMTOM_TOTAL_TIMEOUT_S: Final = 20
TOMTOM_MAX_RETRIES: Final = 3
TOMTOM_BACKOFF_BASE_S: Final = 1.0

# --- Open Charge Map --------------------------------------------------------
# Bron: FASE1-ONDERZOEK-EN-ARCHITECTUUR.md §1.3. Uitsluitend statische
# locatie-/connectordata — nooit als realtime beschikbaarheid tonen.
OCM_API_URL: Final = "https://api.openchargemap.io/v3/poi"
OCM_CONNECT_TIMEOUT_S: Final = 5
OCM_TOTAL_TIMEOUT_S: Final = 20
OCM_MAX_RETRIES: Final = 3
OCM_BACKOFF_BASE_S: Final = 1.0

# --- OpenRouteService (optionele rijafstand-verrijking + routezoeken) ------
# Bron: geverifieerd tegen giscience.github.io/openrouteservice API-referentie,
# openrouteservice-py.readthedocs.io en openrouteservice.org/restrictions
# (2026-07-11). Matrix- en Directions-endpoint, beide POST, header
# "Authorization: <key>" (geen "Bearer"-prefix), coördinaten als [lon, lat].
# Gratis tier: 2.500 requests/dag, 40.000/maand.
ORS_MATRIX_URL_TEMPLATE: Final = "https://api.openrouteservice.org/v2/matrix/{profile}"
# "geojson"-formaat i.p.v. de json-default: levert een gewone GeoJSON
# LineString ([lon, lat]-coördinaten) i.p.v. Google's encoded polyline —
# voorkomt dat we zelf een polyline-decoder moeten schrijven.
ORS_DIRECTIONS_URL_TEMPLATE: Final = (
    "https://api.openrouteservice.org/v2/directions/{profile}/geojson"
)
ORS_PROFILE_DRIVING: Final = "driving-car"
ORS_CONNECT_TIMEOUT_S: Final = 5
ORS_TOTAL_TIMEOUT_S: Final = 15
ORS_MAX_RETRIES: Final = 2
ORS_BACKOFF_BASE_S: Final = 1.0
# Alleen de top-N (op hemelsbrede afstand gesorteerde) kandidaten krijgen een
# echte rijafstand-opvraging — voorkomt onnodig veel API-calls per update
# (opdracht §20, performance-first op Raspberry Pi 4) en blijft ruim binnen
# de matrix-querylimiet (max. 25 locaties bij "dynamische" argumenten).
DRIVING_DISTANCE_TOP_N: Final = 5

# --- Routegebaseerd zoeken --------------------------------------------------
DEFAULT_ROUTE_CORRIDOR_M: Final = 1000
MIN_ROUTE_CORRIDOR_M: Final = 100
MAX_ROUTE_CORRIDOR_M: Final = 5000
# De omsluitende zoekcirkel rond de hele route wordt begrensd tot MAX_RADIUS_M
# (bestaande grens) — voorkomt een onbegrensd grote provideraanvraag bij een
# lange route. Bij een lange route worden de verste segmenten dus niet
# doorzocht; dit is een bewuste, gedocumenteerde grens (geen route-chunking
# in v1, laagste complexiteit — zie opdracht §6/§20).
ROUTE_ENCLOSING_RADIUS_CAP_M: Final = MAX_RADIUS_M

# --- Coordinator ------------------------------------------------------------
UPDATE_FAILURE_STREAK_FOR_REPAIR: Final = 6  # ~6 opeenvolgende mislukkingen

# --- Zone-entrydetectie (Fase 4) --------------------------------------------
# Interne bus-event-naam waarmee zone_tracking.py een gedetecteerde
# zone-entry doorgeeft aan de event-entiteit (event.py) — ontkoppelt
# detectielogica van entity-representatie.
SIGNAL_ZONE_ENTERED: Final = f"{DOMAIN}_zone_entered"
# Beschermt tegen (bijna-)gelijktijdige duplicaatdetecties, bv. wanneer een
# person-entiteit en de daaraan gekoppelde device_tracker binnen dezelfde
# seconde allebei een zone-entry-event afvuren (opdracht §15).
ZONE_ENTRY_DEBOUNCE: Final = timedelta(seconds=5)

# --- Kaartmarkers (geo_location-platform) -----------------------------------
# Statisch geserveerd vanuit custom_components/vun_ev_charge_monitor/markers/
# via hass.http.async_register_static_paths (opdracht: gebruikersverzoek om
# laadlocaties als rood/oranje/groen op een map-kaart te tonen).
MARKERS_URL_PATH: Final = "/vun_ev_charge_monitor_markers"
MARKER_FILE_RED: Final = "marker-red.png"  # 0 beschikbaar
MARKER_FILE_ORANGE: Final = "marker-orange.png"  # 1 beschikbaar
MARKER_FILE_GREEN: Final = "marker-green.png"  # 2 of meer beschikbaar

# --- Events -------------------------------------------------------------
EVENT_TYPE_ZONE_ENTERED: Final = "zone_entered"
EVENT_TYPE_AVAILABILITY_CHANGED: Final = "availability_changed"
EVENT_TYPE_CHARGER_AVAILABLE: Final = "charger_available"
EVENT_TYPE_PROVIDER_UNAVAILABLE: Final = "provider_unavailable"
EVENT_TYPES: Final = (
    EVENT_TYPE_ZONE_ENTERED,
    EVENT_TYPE_AVAILABILITY_CHANGED,
    EVENT_TYPE_CHARGER_AVAILABLE,
    EVENT_TYPE_PROVIDER_UNAVAILABLE,
)

# --- Repairs issue-id's -----------------------------------------------------
ISSUE_ZONE_REMOVED: Final = "zone_removed"
ISSUE_TRACKED_ENTITY_REMOVED: Final = "tracked_entity_removed"
ISSUE_PROVIDER_UNAVAILABLE: Final = "provider_unavailable"
ISSUE_NOTIFICATION_SERVICE_MISSING: Final = "notification_service_missing"

# --- Services ----------------------------------------------------------
# send_test_notification is bewust NIET als service geïmplementeerd — de
# button-entiteit (opdracht §26) dekt dit al volledig, een service zou
# functionele overlap opleveren.
SERVICE_GET_NEARBY_CHARGERS: Final = "get_nearby_chargers"
SERVICE_MAX_RESULTS: Final = 20
