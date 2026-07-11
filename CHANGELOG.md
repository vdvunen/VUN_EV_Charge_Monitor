<!--
Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl
-->

# Changelog

Alle relevante wijzigingen aan dit project worden hier bijgehouden.
Versiebeheer volgt [Semantic Versioning](https://semver.org/).

## [1.4.0] - 2026-07-11

### Toegevoegd
- **Routegebaseerd zoeken** (`route.py`, nieuw): in plaats van rond een vaste straal kan er nu gezocht worden langs een route van de zone naar een tweede zone (`route_destination_zone`, zoekopties-stap). De routegeometrie wordt opgehaald via de OpenRouteService Directions API (`format=geojson`, bring-your-own-key — dezelfde key als de optionele rijafstand-verrijking). Laadlocaties worden vervolgens gefilterd op werkelijke afstand tot de routelijn (`route_corridor_m`, standaard 1000m, instelbaar 100–5000m) i.p.v. op afstand tot één middelpunt.
- Bestaande providerinterface (`ChargeLocationProvider.async_get_locations`) is ongewijzigd: de omsluitende cirkel (middelpunt + straal) rond de volledige route wordt met de bestaande radius-zoekopdracht bevraagd, waarna de coordinator lokaal filtert op afstand-tot-route. Geen providerwijziging nodig.
- In routemodus is `distance_m` de afstand vanaf het startpunt (niet vanaf de routelijn) — consistent met de bestaande "hoe ver moet ik nog rijden vanaf hier"-betekenis van dit veld.
- **Bewust géén stille terugval** bij routefouten (i.t.t. de rijafstand-verrijking): ontbrekende/ongeldige bestemmingszone, ontbrekende OpenRouteService-key, of een mislukte routeaanvraag laten de hele update expliciet mislukken (`UpdateFailed`) — een gewoon straal-resultaat tonen alsof het om een routeresultaat ging zou misleidend zijn.
- Bekende MVP-beperking: het omsluitende zoekgebied wordt begrensd tot de bestaande maximale straal (20 km) — zeer lange routes worden dus niet in segmenten opgeknipt. Voor de meeste dagelijkse woon-werk-routes is dit voldoende; opgenomen als bekende beperking in de gebruikersdocumentatie.
- Nieuwe config-flowfout `missing_routing_key` hergebruikt (tekst uitgebreid: dekt nu zowel rijafstand als routegebaseerd zoeken).
- Tests: `test_route.py` (8 tests: routeparsing, middelpunt/straal-berekening, foutafhandeling, afstand-tot-route), uitbreidingen in `test_coordinator.py` (4 tests: ontbrekende key, ontbrekende bestemmingszone, routefout, corridor-filtering + afstand-herberekening).

### Aanleiding
Gebruikersverzoek (na eerdere providerlogica-toelichting): laadpunten zoeken langs een route van A naar B in plaats van alleen rond een vast punt, bijvoorbeeld voor het plannen van een laadstop onderweg naar een tweede zone.

### Rollback
Verwijder `custom_components/vun_ev_charge_monitor/`, herstel eventueel eerdere back-up, herstart Home Assistant. Bestaande config entries blijven werken zonder het nieuwe veld (`route_destination_zone` leeg = ongewijzigd straal-zoekgedrag, geen breaking change).

## [1.3.0] - 2026-07-11

### Toegevoegd
- **Laadlocaties op de kaart** (`geo_location.py`, nieuw platform): tot `max_results` `geo_location`-entiteiten met de exacte coördinaten van de huidige topresultaten, direct bruikbaar in een standaard Home Assistant `map`-kaart.
- Rood/oranje/groen marker-afbeeldingen (`markers/marker-{red,orange,green}.png`) op basis van het aantal beschikbare aansluitingen (0 / 1 / 2+), geserveerd via `hass.http.async_register_static_paths` (idempotent over meerdere config entries).
- Vaste "slot"-entiteiten (`map_marker_0` .. `map_marker_<max_results-1>`) i.p.v. dynamisch aanmaken/verwijderen per update — een marker toont altijd de huidige #N-locatie en wordt `unavailable` (dus niet op de kaart getoond) zodra er geen locatie meer op die positie staat. Blijft binnen opdracht §17 (geen entity per laadpaal): het aantal is begrensd tot `max_results`, niet tot het totaal aantal gevonden laadpalen.
- Tests: `test_geo_location.py` (kleurlogica + lege-slot-gedrag).

### Aanleiding
Gebruikersverzoek: de gevonden laadpalen visueel op een kaart zien, met een directe rood/oranje/groen-indicatie van beschikbaarheid in plaats van alleen tekstuele sensoren.

### Rollback
Verwijder `custom_components/vun_ev_charge_monitor/`, herstel eventueel eerdere back-up, herstart Home Assistant. Verwijder eventueel handmatig toegevoegde `map`-kaarten met deze entiteiten uit het dashboard — die tonen na verwijdering "entity not found".

## [1.2.0] - 2026-07-11

### Toegevoegd
- **Operator-uitsluitfilter** (`operator_exclude`, zoekopties-stap): sluit specifieke laadnetwerken uit. De sortering had al nooit een merkvoorkeur (beschikbaarheid → afstand → vermogen → actualiteit, operator-onafhankelijk); dit maakt het expliciet configureerbaar in plaats van impliciet gedrag.
- **Optionele rijafstand i.p.v. hemelsbreed** (`use_driving_distance` + `ors_api_key`, zoekopties-stap): nieuwe module `distance.py` haalt echte rijafstand op via de OpenRouteService Matrix API (bring-your-own-key, gratis tier 2.500 requests/dag). Om het API-verbruik laag te houden (opdracht §20, Raspberry Pi 4) wordt dit alleen toegepast op de top-`DRIVING_DISTANCE_TOP_N` (5) kandidaten ná sortering op hemelsbrede afstand, met een re-sortering van uitsluitend die subset op de echte afstand. Faalt nooit hard — elke fout (auth/rate-limit/netwerk/malformed) valt automatisch terug op de ongewijzigde hemelsbrede afstand.
- `ChargeLocation.distance_is_driving`-veld om te onderscheiden of `distance_m` een rijafstand of een hemelsbrede afstand is.
- `ApiClient.async_post_json()` — de HTTP-client ondersteunde tot nu toe alleen GET; de OpenRouteService Matrix API vereist een POST met JSON-body. Retry/back-off/foutafhandeling is gedeeld met de bestaande GET-implementatie (`_async_request_json`).
- Nieuwe config-flowfout `missing_routing_key`: rijafstand aanzetten zonder OpenRouteService-key wordt geblokkeerd vóór opslag.
- Tests: `test_distance.py` (10 tests, volledig geverifieerd), uitbreidingen in `test_api.py` (POST-ondersteuning) en `test_coordinator.py` (operator-filter, driving-distance-wiring).

### Aanleiding
Rechtstreeks n.a.v. gebruikersfeedback tijdens live-gebruik: de "beste laadlocatie" bleek een specifieke operator te tonen zonder dat duidelijk was dat de keuze al merk-onafhankelijk was, en de getoonde afstand (bewust hemelsbreed, zie Fase 1-architectuurkeuze) werd verward met de langere routeafstand die Google Maps na het klikken op de navigatielink berekent.

### Rollback
Verwijder `custom_components/vun_ev_charge_monitor/`, herstel eventueel eerdere back-up, herstart Home Assistant. Bestaande config entries blijven werken zonder de nieuwe velden (vallen terug op hun defaults: geen operator-uitsluiting, hemelsbrede afstand).

## [1.1.0] - 2026-07-11

### Toegevoegd
- Brand-icoon (`custom_components/vun_ev_charge_monitor/brand/icon.png`, 256×256, en `icon@2x.png`, 512×512, transparante achtergrond): drie afgeronde blokken "V·U·N", middelste blok in mint aqua met een bliksem-accent, buitenste blokken in Pruisischblauw. Gekozen na een verkenning van 5 richtingen. Wordt door Home Assistant automatisch geserveerd via `/api/brands/integration/vun_ev_charge_monitor/icon.png` zodra de `brand/`-map aanwezig is — geen pull request naar `home-assistant/brands` nodig.

### Rollback
Verwijder `custom_components/vun_ev_charge_monitor/brand/` om terug te vallen op het standaard Home Assistant-integratie-icoon. Geen functionele impact, puur visueel.

## [1.0.3] - 2026-07-11

### Bugfix (kritiek)
- **NDW-provider (`providers/ndw.py`)**: de live API plaatst `id` als lid van het GeoJSON Feature-object zelf (naast `geometry`/`properties`), niet binnen `properties` zoals de code aannam. Hierdoor faalde `properties.get("id")` voor **elke** locatie, en werd de complete respons stilzwijgend als "ongeldig" afgewezen — resultaat: altijd 0 laadlocaties gevonden, ongeacht echte NDW-dekking. Gevonden door een gebruikersmelding te herleiden: eerst leek het een radius-/providerkeuzeprobleem (gebruiker stond op Open Charge Map, dat inherent geen bezettingsdata heeft — geen bug), maar na omzetten naar NDW bleef "0 gevonden" bestaan. De live payload is vervolgens letterlijk door onze eigen parsingcode gehaald (163 raw features → 0 geparste locaties), wat de exacte breukregel blootlegde.
- Opgelost door `feature.get("id")` als primaire bron te gebruiken, met `properties.get("id")` als defensieve fallback. `evse_id`-constructie in `_build_evses()` gebruikt nu ook de correct opgeloste `location_id` i.p.v. de altijd-lege `properties["id"]`.
- Fixture (`tests/fixtures/ndw_response.json`) en `test_providers.py` bijgewerkt om de echte Feature-structuur te weerspiegelen, met een expliciete regressietest voor beide id-locaties (Feature-niveau primair, properties-niveau als fallback).
- Geverifieerd tegen een echte live NDW-respons (163 features rond een gebruikerslocatie): na de fix worden 38 locaties binnen 1500m correct gevonden met kloppende beschikbaarheids- en vermogenscijfers.

### Rollback
Verwijder `custom_components/vun_ev_charge_monitor/`, herstel eventueel eerdere back-up, herstart Home Assistant. Geen config-entry-impact. **Let op:** terugzetten naar v1.0.2 of eerder herintroduceert de "altijd 0 laadlocaties met NDW"-bug.

## [1.0.2] - 2026-07-11

### Bugfix
- **NDW-provider (`providers/ndw.py`)**: `power_max` uit de live NDW DOT-NL-respons staat in **Watt**, niet kW. Hierdoor toonden sensoren en notificaties het maximale laadvermogen 1000x te hoog (bv. "22080 kW" i.p.v. "22 kW"). Gevonden en bevestigd door de live API daadwerkelijk aan te roepen (bbox rond Amsterdam, 2026-07-11) na een gebruikersmelding over afwijkende beschikbaarheidscijfers t.o.v. Google Maps. Opgelost door `power_max` te delen door 1000 vóór opslag in het interne model.
- Twee van de drie in Fase 1 gemarkeerde NDW-aannames zijn hiermee alsnog geverifieerd tegen een echte respons: de live API vereist geen authenticatie, en de veldnamen (`availabilities[]`, `available`, `total`, `connector_type`, `power_max`) kloppen exact. Bijgewerkt in `providers/ndw.py`-moduledocstring en `tests/fixtures/ndw_response.json` (realistische Watt-waarden i.p.v. reeds-in-kW-waarden).

### Rollback
Verwijder `custom_components/vun_ev_charge_monitor/`, herstel eventueel eerdere back-up, herstart Home Assistant. Geen config-entry-impact; terugzetten naar v1.0.1 herstelt de vermogens-weergavebug maar heeft verder geen risico.

## [1.0.1] - 2026-07-11

### Gewijzigd
- `manifest.json`: `codeowners`, `documentation` en `issue_tracker` bijgewerkt naar de echte, publieke repository: https://github.com/vdvunen/VUN_EV_Charge_Monitor (was een placeholder-adres).
- `PRODUCTION_CHECK.md` bijgewerkt: HACS-manifestvelden zijn nu correct; de daadwerkelijke HACS-validatie-workflow zelf is nog niet uitgevoerd (aanbevolen als eerste CI-stap).

### Rollback
Verwijder `custom_components/vun_ev_charge_monitor/`, herstel eventueel eerdere back-up, herstart Home Assistant. Zuiver metadata-/documentatiewijziging — geen functionele of config-entry-impact, terugzetten naar v1.0.0 is zonder risico.

## [1.0.0] - 2026-07-10

Eerste stabiele release. Alle zes fases uit de opdracht zijn opgeleverd.

### Toegevoegd
- Volledige documentatieset: `USER_DOCUMENTATION.md`, `SETUP_DOCUMENTATION.md`, `User_Documentation.docx`, `IMPACT_ANALYSIS.md`, `PRODUCTION_CHECK.md`, uitgebreide `README.md`.
- Repair-opruiming: alle repair issues van een config entry worden nu verwijderd bij unload/verwijdering (`repairs.async_clear_all_issues_for_entry`) — voorkomt achterblijvende "spooksignalen" in de issue registry.
- Info-niveau logging bij succesvolle setup (provider + entry-titel, geen gevoelige data).

### Gewijzigd / Security
- **Beveiligingsfix**: `api.py` interpoleerde in enkele foutmeldingen de volledige tekst van onderliggende `aiohttp`-excepties. Voor `ContentTypeError` embedt die tekst de complete requeststring inclusief querystring — en TomTom verstuurt zijn API-key als queryparameter. Hierdoor kon een API-key in theorie in de Home Assistant-log terechtkomen via de foutmeldingketen (`api.py` → `providers/*.py` → `coordinator.py` → HA's coordinator-warninglog). Opgelost door nergens meer de ruwe exceptietekst over te nemen, alleen het exceptietype (`api.py::_safe_exc_text`). Ook `config_flow.py`'s generieke fout-handler gebruikt niet langer `_LOGGER.exception()` (volledige traceback) maar logt alleen het exceptietype.
- Bugfix: `CONF_LANGUAGE` werd gebruikt in `config_flow.py` zonder geïmporteerd te zijn — de notificatiestap van de config/optionsflow crashte zodra deze daadwerkelijk gerenderd werd. Gevonden via een `pyflakes`-pas tijdens de Fase 6-reviewpass (niet gevonden door losse module-imports, omdat de fout pas bij functie-aanroep optrad).
- Dode code opgeruimd: ongebruikte constanten `PLATFORM_*`, `MAX_ZONE_RADIUS_LOOKUP_M`, `ERROR_NO_REALTIME_AVAILABILITY` (en bijbehorende, nooit-gekoppelde vertaalstrings) verwijderd.
- `manifest.json`-versie bijgewerkt naar `1.0.0`.

### Bekende beperkingen (zie PRODUCTION_CHECK.md voor volledige details)
- NDW-authenticatiemodel en exacte per-EVSE-statusgranulariteit zijn nog niet tegen een echte live-respons geverifieerd.
- De volledige testsuite kon in de Windows-ontwikkelomgeving van deze sessie niet 100% via `pytest` uitgevoerd worden (bekende HA-op-Windows-beperking, geen codefout) — aanbevolen om vóór publicatie eenmalig in WSL2/Docker/CI te draaien.
- `manifest.json`'s `codeowners`/`documentation`/`issue_tracker` bevatten een placeholder-GitHub-adres — vervang dit door het echte repository-adres vóór HACS-publicatie.

### Rollback
Verwijder `custom_components/vun_ev_charge_monitor/`, herstel eventueel eerdere back-up, herstart Home Assistant. Config entries blijven op `version = 1` — geen datamigratie nodig bij terugzetten naar v0.5.0.

## [0.5.0] - 2026-07-10

### Toegevoegd
- TomTom-provider (`providers/tomtom.py`) — EV Search API, per-EVSE-status rechtstreeks uit de respons (geen synthetische benadering nodig zoals bij NDW).
- Open Charge Map-provider (`providers/open_charge_map.py`) — statische locatie-/connectordata, `realtime_data_available` altijd `False`.
- Gedeelde providerhelpers (`providers/_common.py`): connectortypemapping en navigatie-URL-opbouw, hergebruikt door NDW/TomTom/OCM (voorkomt dubbele logica).
- Providerselectie in `__init__.py` uitgebreid naar alle drie providers plus simulatiemodus.
- Service `vun_ev_charge_monitor.get_nearby_chargers` (`services.py`/`services.yaml`) met begrensde, geredacteerde service-response.
- Tests voor beide nieuwe providers en de service.

### Gewijzigd
- `SUPPORTED_PROVIDERS` uitgebreid; TomTom/Open Charge Map vereisen verplicht een API-key (afgedwongen door de providers zelf via `ProviderAuthError`, geen dubbele validatielogica in de config flow).

### Rollback
Verwijder `custom_components/vun_ev_charge_monitor/`, herstel eventueel eerdere back-up, herstart Home Assistant. Bestaande config entries met provider `ndw` blijven ongewijzigd werken bij terugzetten naar v0.3.0.

## [0.4.0] - 2026-07-10

### Toegevoegd
- Zone-entrydetectie (`zone_tracking.py`): async state-listeners op gevolgde `person`/`device_tracker`-entiteiten, met startup-guard, transitiecontrole, debounce (5s) en cooldown (instelbaar).
- Notificatielogica (`notifications.py`): drie meldingvarianten (beschikbaar/niets beschikbaar/alleen statische data) in NL/EN, verstuurd via `notify.send_message`.
- Simulatiemodus (`providers/simulation.py`, `CONF_SIMULATION_MODE`): lokale testdata, geen externe API-calls; providertest in de config/options flow wordt overgeslagen wanneer actief.
- Testmelding-button (`button.py`: `VunEvTestNotificationButton`) — verstuurt direct een melding, los van cooldown/toggles.
- `zone_entered`-event nu daadwerkelijk gevuld via een intern bus-signaal (`SIGNAL_ZONE_ENTERED`) tussen `zone_tracking.py` en `event.py`.
- Repair "notificatiedoel ontbreekt" (`ISSUE_NOTIFICATION_SERVICE_MISSING`), periodiek gecontroleerd door de coordinator.
- `CoordinatorData.radius_m` toegevoegd zodat de notificatietekst exact dezelfde radius toont als daadwerkelijk gebruikt bij het zoeken.
- Tests: `test_notifications.py`, `test_zone_tracking.py`.

### Rollback
Verwijder `custom_components/vun_ev_charge_monitor/`, herstel eventueel eerdere back-up, herstart Home Assistant. Config entries van v0.3.0 blijven werken na terugzetten (nieuwe velden krijgen simpelweg hun default terug via `_get_config_value`-fallback).

## [0.3.0] - 2026-07-10

### Toegevoegd
- Options flow (`VunEvChargeMonitorOptionsFlow`, `OptionsFlowWithReload`) — alle instelbare velden uit de config flow zijn achteraf wijzigbaar (opdracht §12).
- Reauth-flow (`async_step_reauth`/`async_step_reauth_confirm`) — wordt automatisch getriggerd via `ConfigEntryAuthFailed` vanuit de coordinator bij HTTP 401/403.
- Reconfigure-flow (`async_step_reconfigure`) — hergebruikt dezelfde stappen als de initiële config flow.
- Retries met exponentiële back-off en HTTP 429/`Retry-After`-afhandeling in `api.py` (`ApiClient`).
- Stale-datadetectie (`coordinator.is_stale`, `binary_sensor.data_stale`) op basis van geconfigureerde maximumleeftijd.
- Diagnostics (`diagnostics.py`) met volledige redactie van API-keys, zone, gevolgde entiteiten en notificatiedoel.
- Repairs (`repairs.py`) voor verwijderde zone, verwijderde gevolgde entiteit en langdurig onbereikbare provider.
- Volledige foutafhandeling in coordinator en config/options flow (invalid_auth, cannot_connect, rate_limited, invalid_zone, invalid_entity, invalid_radius, invalid_interval, invalid_notification_service, unsupported_provider, unknown).
- Uitgebreide testsuite (config flow, coordinator, diagnostics, providers, API-client, lifecycle).

### Gewijzigd
- Coordinator behoudt nu expliciet de laatst geldige dataset bij providerfouten (`UpdateFailed`) i.p.v. entities "unavailable" te maken.

### Bekende beperkingen
- Zie FASE1-ONDERZOEK-EN-ARCHITECTUUR.md §7: authenticatiemodel van de live NDW-API en exacte per-EVSE statusgranulariteit zijn nog niet tegen een echte respons geverifieerd (geen testomgeving met live NDW-toegang beschikbaar in deze fase).
- Zone-entry-detectie, notificatieverzending en simulatiemodus zijn nog niet geïmplementeerd — gepland voor Fase 4.

### Rollback
Verwijder `custom_components/vun_ev_charge_monitor/`, herstel eventueel eerdere back-up, herstart Home Assistant. Config entries van v0.3.0 zijn config-entry-`version` 1 — geen migratie uitgevoerd, dus terugzetten naar v0.2.0 vereist geen datamigratie terug.

## [0.2.0] - 2026-07-10

### Toegevoegd
- Eerste werkende integration: manifest, constants, intern datamodel (`models.py`), providerabstractie (`providers/base.py`), NDW DOT-NL-provider (`providers/ndw.py`), generieke API-client (`api.py`), `DataUpdateCoordinator` (`coordinator.py`).
- Config flow (`config_flow.py`) volledig via de UI: zone, provider/API-key, gevolgde personen/device trackers, zoekopties, notificatie-instellingen.
- Basisentiteiten: sensoren (`sensor.py`), binary sensors (`binary_sensor.py`), refresh-button (`button.py`), event-entiteit (`event.py`).
- Nederlandse en Engelse vertalingen (`strings.json`, `translations/nl.json`, `translations/en.json`).
- Basistests en basisdocumentatie.

## [0.1.0] - 2026-07-10

### Toegevoegd
- Fase 1 — Onderzoek en architectuur (`FASE1-ONDERZOEK-EN-ARCHITECTUUR.md`): providerresearch (NDW DOT-NL, TomTom, Open Charge Map, OCPI), beslisbomen, intern datamodel, Home Assistant-architectuurkeuzes, projectstructuur, risico- en impactanalyse. Nog geen integrationcode.
