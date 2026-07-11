<!--
Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl
-->

# Fase 1 — Onderzoek en Architectuur

**Project:** VUN EV Charge Monitor (Home Assistant custom integration)
**Datum onderzoek:** 2026-07-10
**Status:** Afgerond — geen integrationcode geschreven in deze fase (conform opdracht §40 Fase 1)

Alle onderstaande bevindingen zijn geverifieerd tegen officiële bronnen (developers.home-assistant.io, hacs.xyz, ndw.nu/docs.ndw.nu, developer.tomtom.com, openchargemap.org, evroaming.org, github.com/ocpi/ocpi) op 2026-07-10. Aannames zijn expliciet gemarkeerd in §7.

---

## 1. Providerresearch

### 1.1 NDW DOT-NL — Primaire kandidaat

- **Bestaat en is actueel**: DOT-NL ("Dataplatform Openbaar Toegankelijke laadpunten – Nederland") is het officiële Nationaal Toegangspunt (NAP) voor Nederlandse publieke laadpuntdata, in opdracht van het Ministerie van I&W, beheerd door NDW, wettelijk verplicht onder AFIR.
  Bronnen: ndw.nu/producten-en-diensten/dataportalen/dot-nl, docs.ndw.nu/faq/DOT-NL
- **Live API**: `GET https://dotnl.ndw.nu/api/rest/geojson/dynamic-road-status/charge-point-data/v1/features` met `?bbox=minLon,minLat,maxLon,maxLat` (max 1.0°² gebied, max 1000 features/request, 10 req/sec rate limit, HTTP 429 bij overschrijding).
- **Bulk static downloads** (geen auth): `opendata.ndw.nu/charging_point_locations.geojson.gz` (~3,7 MB), `charging_point_locations_ocpi.json.gz` (~14 MB, OCPI 2.2.1-vormig), `charging_point_tariffs_ocpi.json.gz` (~3,4 MB).
- **Actualiteit**: wettelijk verplichte SLA van ≤1 minuut voor dynamische data (AFIR).
- **Response bevat**: `id`, geometry, adres, `cpo_id`, `operator_name`, `open`, `last_updated`, `availabilities[]` (per connectortype: `available`, `total`, `connector_type`, `connector_format`, `power_max`, `power_type`, `tariff_ids`).
- **Licentie**: kosteloos voor iedereen, geen formele CC-licentienaam gevonden op officiële pagina's.
- **Verwant maar NIET geschikt**: LINDA (ook NDW) is een historisch-sessiedataportaal met dagelijkse/tweewekelijkse pull-intervallen — niet realtime, niet bruikbaar voor deze integration.

### 1.2 TomTom — Tweede kandidaat (bring-your-own-key)

- **EV Search API** (`GET /search/2/evsearch`) + **EV Charging Stations Availability API** (`GET /search/2/chargingAvailability`, gekoppeld via `dataSources.chargingAvailability`-UUID uit de search-response) zijn twee gescheiden endpoints.
- **Auth**: API-key als query-param `key=`.
- **Realtime data**: ververst circa elke 3 minuten; aggregatie per connectortype + vermogensband (niet per individuele connector-ID) via de Availability-API; de Search-API zelf levert wél `chargingPoints[]` met `evseId`, `status` (Available/Occupied/Reserved/OutOfService/Unknown) per punt.
- **Rate limits**: standaard Search API 5 QPS, EV Search API 25 QPS; **EV Search API is expliciet uitgesloten van het gratis evaluatietier** — pricing vereist salescontact (onbevestigd, zie §7).
- **ToS**: caching van resultaten is contractueel beperkt tot wat `cache-control`-headers toestaan (Terms clausule 11.4) — geen vrije lokale caching voor schaaldoeleinden.
- **NL-dekking**: officieel gemarkeerd als ondersteund (EV Static + EV Dynamic) in de Market Coverage-tabel.
- **ID-scheme**: `evseId` (OCPI-achtig, bv. `NL-GFX-ETNLP011512-1`) bruikbaar voor cross-provider matching.

### 1.3 Open Charge Map — Fallback

- **Endpoint**: `GET https://api.openchargemap.io/v3/poi` met `latitude`, `longitude`, `distance`, `maxresults`, `countrycode`, etc.
- **Auth**: sinds kort **verplicht** — gratis API-key via `X-API-Key`-header of `key`-query-param (live geverifieerd: zonder key → HTTP 403).
- **Realtime beschikbaarheid**: **NIET aanwezig.** `StatusTypeID` is operationele status (werkend/kapot), niet bezetting; `DateLastVerified`/`IsRecentlyVerified` zijn crowdsourced/handmatige checks, geen live feed. Moet in de integration altijd worden gelabeld als "laatst bekende locatie-informatie, geen actuele bezetting."
- **Rate limits**: geen harde cijfers, alleen een Fair Usage Policy (debounce, custom User-Agent, risico op automatische ban bij excessief gebruik).
- **Licentie**: gemengd per record — eigen OCM-data CC BY 4.0, geïmporteerde providerdata behoudt eigen licentie (zichtbaar per POI in `DataProvider.License`); filter `opendata=true` voor bevestigd open-licentie data.
- **ID-scheme**: integer `ID` + `UUID`; geen directe OCPI EVSE-ID-koppeling.

### 1.4 OCPI / EVRoaming Foundation — Datamodel-referentie

- **Actuele versie**: OCPI 2.3.0 (feb. 2025, AFIR-conform); 2.2.1 nog breed in gebruik (o.a. NDW DOT-NL); 3.0 in draft.
- **Hiërarchie**: `Location` bevat één of meer `EVSE`'s; elke `EVSE` bevat één of meer `Connector`'s. **Kritiek**: connectoren op dezelfde EVSE kunnen NIET gelijktijdig gebruikt worden — "only one connector per EVSE can be used at the time." Dit betekent: tel beschikbaarheid per EVSE, niet per connector, om dubbeltelling te voorkomen (lost de open vraag uit opdracht §10 op).
- **Officiële Status-enum**: `AVAILABLE, BLOCKED, CHARGING, INOPERATIVE, OUTOFORDER, PLANNED, REMOVED, RESERVED, UNKNOWN` — vrijwel 1-op-1 met het interne model uit opdracht §10 (BLOCKED → mapt op `occupied`).
- **Toegangsmodel**: OCPI is een B2B-roamingprotocol tussen CPO's en eMSP's met bilaterale contracten — geen publieke anonieme toegang tot losse CPO-feeds. DOT-NL is de legale, publieke aggregator die dit omzeilt (geen registratie/contract nodig voor consumenten).

---

## 2. Beslisboom — Providerstrategie

**Optie A — NDW DOT-NL als enige primaire bron (MVP).**
Voordelen: officieel, gratis, wettelijk gegarandeerde actualiteit (≤1 min), server-side bbox-filtering (lage resourcebelasting op RPi4), OCPI-vormige data (herbruikbare statusnormalisatie).
Nadelen: live-API-authenticatie en exacte per-EVSE statusgranulariteit nog niet volledig bevestigd (zie §7, aannames).

**Optie B — TomTom als primaire bron.**
Voordelen: bevestigde per-EVSE/connector statusgranulariteit met `evseId`.
Nadelen: geen gratis tier voor deze specifieke API's, verplicht bring-your-own-key (matcht wel opdracht §7.2), cachingbeperking in ToS. Ongeschikt als *primaire* bron voor een out-of-the-box werkende integration zonder configuratie.

**Optie C — Open Charge Map als primaire bron.**
Nadelen: geen realtime bezetting — expliciet buiten scope voor "actuele beschikbaarheid" (opdracht §3/§7.3). Ongeschikt als primair.

**Optie D — Direct combineren van bronnen met confidence score in MVP.**
Nadelen: verhoogt complexiteit en resourcebelasting aanzienlijk; opdracht §8 zegt expliciet "Kies uiteindelijk één primaire implementatie voor de eerste werkende versie."

**Definitieve keuze: Optie A.** NDW DOT-NL is de primaire en enige provider voor de MVP (Fase 2–4). TomTom wordt in Fase 5 toegevoegd als optionele bring-your-own-key-bron voor gebruikers die per-EVSE-granulariteit willen. Open Charge Map wordt in Fase 5 toegevoegd als losstaande fallback voor statische locatiedata, expliciet gelabeld als "geen actuele bezetting" — nooit stilzwijgend gecombineerd met NDW-data (voorkomt onbetrouwbare naam-matching, conform opdracht §8.5).

---

## 3. Beslisboom — Home Assistant architectuurkeuzes

| Keuze | Opties overwogen | Definitief | Onderbouwing |
|---|---|---|---|
| Config entry state | Instance-attributen op `hass.data[DOMAIN]` vs. `ConfigEntry.runtime_data` | `runtime_data` | Huidige officiële aanbeveling; automatische cleanup bij unload, geen globale mutable state (conform opdracht §28) |
| Options flow basisklasse | `OptionsFlowWithConfigEntry` (legacy) vs. `OptionsFlowWithReload` | `OptionsFlowWithReload` | `OptionsFlowWithConfigEntry`-patroon (`self.config_entry = config_entry`) is hard-deprecated en verwijderd per HA 2025.12; `OptionsFlowWithReload` regelt reload automatisch, geen handmatige update-listener nodig |
| Zone-selectie in config flow | Custom `ZoneSelector` (bestaat niet) vs. `EntitySelector(domain="zone")` vs. `LocationSelector` (vrije kaartpicker) | `EntitySelector(domain="zone")` | Opdracht vereist hergebruik van *bestaande* HA-zones (§2.4, §14), niet een vrije puntkeuze; `ZoneSelector` bestaat niet in de HA-selector-broncode |
| Afstandsberekening | Zelf Haversine implementeren (zoals gesuggereerd in opdracht §14) vs. HA-native `homeassistant.util.location.distance()` | HA-native | Opdracht §14 zegt zelf: "Voeg hiervoor geen externe geografische dependency toe wanneer native Python voldoende is" — HA's ingebouwde `util.location.distance()`/`vincenty()` en `zone.in_zone()`/`async_active_zone()` zijn native, geteste, `@lru_cache`-geoptimaliseerde helpers; zelf implementeren zou dubbele logica zijn (afwijking t.o.v. letterlijke suggestie in opdracht, met expliciete onderbouwing — laagste complexiteit) |
| "Iets is gebeurd"-signalen (zone entry, beschikbaarheid gewijzigd) | Alleen `hass.bus.async_fire` vs. `event`-platform entity | `EventEntity` (event-platform) | Officiële HA-richtlijn: event-entities verdienen de voorkeur boven kale bus-events voor discoverability/UX; bus-events blijven gereserveerd voor systeeminterne signalen |
| Notificatieservice-aanroep | Legacy `notify.notify` vs. `notify.send_message` met `target` | `notify.send_message` + `TargetSelector` | `notify.notify` is expliciet afgeraden ("shorthand for the first notify action found", onvoorspelbaar); `TargetSelector` laat gebruiker entity/device/area/label kiezen, generiek en toekomstvast |
| Device-type in registry | `entry_type` default vs. `DeviceEntryType.SERVICE` | `DeviceEntryType.SERVICE` | Integration modelleert een cloud-service (publieke API), geen fysiek apparaat |
| Reauth/reconfigure koppeling | Losse flow-start vs. entry-gebonden flow (`_get_reauth_entry()`/`_get_reconfigure_entry()`) | Entry-gebonden | Niet-gekoppelde flow-starts zijn deprecated en falen per HA 2025.12 |

---

## 4. Intern datamodel (definitief, zie ook opdracht §9–§10)

Gebaseerd op de bevestigde OCPI-hiërarchie (§1.4): **Location → EVSE → Connector**, met EVSE als telbare eenheid voor "beschikbare aansluiting" (voorkomt dubbeltelling van niet-gelijktijdig bruikbare connectoren op dezelfde EVSE).

Statusnormalisatie mapt direct op de OCPI-status-enum (1-op-1 met opdracht §10's gewenste set):
`available, occupied, charging, reserved, out_of_order, inoperative, unknown, planned, removed`

Regels (ongewijzigd t.o.v. opdracht §10, nu met bronbevestiging):
- Alleen `available` telt als beschikbaar.
- `unknown` en ontbrekende realtime data tellen nooit als beschikbaar.
- `out_of_order`/`inoperative` tellen nooit mee.
- Onderscheid location (NDW `Location`) vs. EVSE (telbare laadpaal-eenheid) vs. connector (fysieke aansluiting, niet los telbaar) wordt expliciet gedocumenteerd in `models.py`-docstring bij implementatie (Fase 2).

`realtime data beschikbaar`-vlag: `true` zolang de bron (NDW live API) een `availabilities[]`-blok met recente `last_updated` levert; `false` zodra alleen statische OCM-data aanwezig is — rechtstreeks bruikbaar voor de drie voorbeeldmeldingen uit opdracht §3.

---

## 5. Home Assistant-architectuur (definitief voor Fase 2+)

- **Config entry**: `runtime_data`, versiebeheer met `version`/`minor_version`, `async_migrate_entry` vanaf eerste breaking wijziging.
- **Coordinator**: één `DataUpdateCoordinator` per config entry; `_async_setup()` voor eenmalige init (API-client, sessie); `_async_update_data()` met `UpdateFailed` bij fouten (behoudt laatste geldige data automatisch); handmatige refresh via button-entity → `coordinator.async_request_refresh()`.
- **Config/options flow**: selectors zoals in §3; entity-selector met domeinfilter `["person","device_tracker"]`, `NumberSelector` voor radius/vermogen/interval, `SelectSelector` voor provider/connectortypen, `TargetSelector` voor notificatiedoel.
- **Diagnostics**: `async_get_config_entry_diagnostics` + `async_redact_data` met `TO_REDACT` = API-keys, coördinaten, notification targets, person/device_tracker entity-ID's.
- **Repairs**: `ir.async_create_issue` alleen voor structurele, actiegerichte problemen (ongeldige/verlopen API-key, verwijderde zone/persoon/tracker, ontbrekende notification service, provider langdurig onbereikbaar) — niet voor transiënte netwerkfouten (die blijven `UpdateFailed` + warning-log).
- **Events**: `EventEntity`-platform voor zone_entered, availability_changed, charger_available, provider_unavailable; events worden gevuurd vanuit coordinator-/`__init__.py`-logica, niet vanuit entity-code zelf.
- **Notificaties**: `notify.send_message` via `hass.services.async_call` met `target`-dict uit de geconfigureerde `TargetSelector`.
- **Zone/afstand**: hergebruik `homeassistant.components.zone.in_zone`/`async_active_zone` en `homeassistant.util.location.distance`.
- **Sessie**: gedeelde `async_get_clientsession(hass)`.
- **Manifest**: `integration_type: "service"`, `iot_class: "cloud_polling"` — beide bevestigd correct; `version` verplicht voor HACS custom; requirements strikt gepind.
- **Testing**: `pytest-homeassistant-custom-component` + `MockConfigEntry` + `enable_custom_integrations`-fixture; testmap spiegelt `custom_components/vun_ev_charge_monitor/`-structuur.
- **HACS**: publieke GitHub-repo, `hacs.json` (minimaal `name`), GitHub Releases i.p.v. alleen default-branch, brand-icoon via lokale `brand/`-map (HA 2026.3+ patroon i.p.v. PR naar `home-assistant/brands`, welke geen custom-integraties meer accepteert).

---

## 6. Projectstructuur

Zoals vastgelegd in opdracht §29 — geen wijzigingen nodig na architectuuronderzoek. Alle genoemde bestanden (inclusief `providers/` submap met `base.py`, `ndw.py`, `tomtom.py`, `open_charge_map.py`) blijven gehandhaafd; geen overbodige bestanden geïdentificeerd. `tomtom.py` en `open_charge_map.py` worden pas in Fase 5 gevuld, maar de mapstructuur wordt in Fase 2 al aangelegd (lege providerklasse met `NotImplementedError` is niet toegestaan als placeholder — deze bestanden worden pas aangemaakt zodra Fase 5 start, niet eerder, om lege placeholders te vermijden conform opdracht §42).

---

## 7. Aannames — expliciet gemarkeerd (te verifiëren in Fase 2 als spike vóór providerimplementatie)

1. **NDW live-API-authenticatie onbevestigd.** De bulk `.gz`-bestanden op `opendata.ndw.nu` vereisen geen key; voor `dotnl.ndw.nu` (live bbox-API) is het exacte auth-mechanisme niet gevonden in publiek toegankelijke documentatie (mogelijk registratie via NDW Servicedesk, "Token-C" genoemd in de FAQ). **Actie Fase 2**: eerste taak is een spike om dit te bevestigen — indien registratie met doorlooptijd nodig is, kan dit Fase 2 vertragen; fallback is starten op de bulk static download + periodieke server-side bbox-filtering in de coordinator zelf.
2. **Exacte statusgranulariteit NDW onbevestigd.** Bevestigd: aggregated `available`/`total` per connectortype per locatie. Niet bevestigd: volledige per-EVSE OCPI-status-enum (AVAILABLE/CHARGING/OUTOFORDER/etc.) in de live feed. **Actie Fase 2**: Swagger-spec (`docs.ndw.nu/.../dafne_api_supplier_push/swagger-bb13f1ca`) inspecteren vóór de normalisatielaag in `providers/ndw.py` wordt afgerond.
3. **TomTom pricing onbevestigd** voor EV Search/Availability API's specifiek (uitgesloten van standaard gratis tier). Geen blocker voor MVP — blijft bring-your-own-key, buiten Fase 2–4 scope.
4. **OCM NL-dekkingskwaliteit onbevestigd** (geen officieel gepubliceerde cijfers). Aanvaardbaar risico voor een fallback-databron in Fase 5.
5. **HACS brand-icoon-flow in transitie** (lokale `brand/`-map sinds HA 2026.3, met een bekende open dashboardbug in de HACS-icoonresolutie). Esthetisch risico, geen functionele blocker.

Geen van deze aannames blokkeert Fase 2 — allen zijn opgenomen als verificatietaak/spike aan het begin van Fase 2, vóór de providerimplementatie wordt afgerond.

---

## 8. Risicoanalyse

- **API-afhankelijkheid**: NDW is single point of failure voor de MVP. Mitigatie: coordinator behoudt laatste geldige data bij tijdelijke fouten, markeert deze als verouderd na ingestelde maximumleeftijd (opdracht §19), repair-issue bij langdurige onbereikbaarheid.
- **Datakwaliteit**: aggregated in plaats van per-EVSE status (aanname 2) kan leiden tot minder precieze "welke exacte aansluiting is vrij"-informatie in de MVP; acceptabel omdat de opdracht primair vraagt om aantallen en dichtstbijzijnde locatie, niet om individuele connector-selectie.
- **Rate limits**: NDW 10 req/sec ruim voldoende voor een enkele periodieke coordinator-poll; OCM fair-use-beleid vereist lange cache-intervallen (Fase 5) om banrisico te vermijden.
- **Privacy**: person/device_tracker-states worden verwerkt — nooit op info-niveau loggen, geen bewegingshistorie opslaan, coordinator bewaart uitsluitend de laatste zone-status (geen tijdreeks), diagnostics redacteert coördinaten en notification targets (opdracht §22/§24).
- **Raspberry Pi 4-belasting**: laag door server-side bbox-filtering (NDW), begrensde resultaten, geen pandas/numpy/zware GIS-library, geen entity-per-laadpaal (voorkomt recorder-spam, opdracht §17/§20).
- **Technische schuld**: door direct `OptionsFlowWithReload` en `runtime_data` te gebruiken i.p.v. de legacy patronen wordt vooraf al voorkomen dat de integration bij HA 2025.12 breekt.

---

## 9. Impactanalyse

- **Bestanden**: geen bestaande bestanden geraakt — greenfield project, lege directory.
- **Configuratie**: nog n.v.t.; Fase 2 introduceert config-entry-schema (zone, personen/trackers, radius, interval, notificatiedoel).
- **Dependencies**: geen runtime-dependency nodig buiten HA/Python-stdlib (zie §10). Dev-only: `pytest-homeassistant-custom-component`.
- **API-koppelingen**: nieuw — NDW DOT-NL (Fase 2), TomTom + OCM (Fase 5, optioneel).
- **Authenticatie**: nog n.v.t. voor NDW bulk-pad; mogelijk API-key-registratie voor live NDW-pad (aanname 1) en verplicht voor OCM (Fase 5) en TomTom (Fase 5, bring-your-own-key).
- **Logging/documentatie/deployment/gebruikers**: nog n.v.t. — worden vanaf Fase 2 opgebouwd.
- **Recorder**: geen impact gepland (geen entity-per-laadpaal, compacte attributen conform opdracht §17).

---

## 10. Dependencies

Geen nieuwe runtime-dependencies nodig. Home Assistant/Python-stdlib volstaat volledig voor Fase 2 (HTTP via HA's gedeelde `aiohttp`-sessie, afstandsberekening via `homeassistant.util.location`, geen JSON/GeoJSON-parsing-library nodig buiten stdlib `json`).

| Dependency | Versie | Doel | Reden | Nativealternatief overwogen | Risico |
|---|---|---|---|---|---|
| `pytest-homeassistant-custom-component` | laatste compatibele met doel-HA-versie (te pinnen in `requirements_test.txt` bij Fase 2) | Testutilities voor custom_component | Spiegelt HA-core testplugins, dagelijks bijgewerkt | Zelfgebouwde test-fixtures | Laag — dev-only, geen productie-impact, onderhouden door community, wordt gepind |

Volledige onderbouwing volgt in `DEPENDENCIES.md` bij Fase 2-oplevering.

---

## 11. Rollback

N.v.t. voor Fase 1 — er is geen code of configuratie gewijzigd in een draaiende Home Assistant-omgeving. Dit onderzoeksdocument kan zonder impact worden aangepast of verwijderd bij vervolgfases.

---

## 12. Productiecheck (Fase 1-niveau)

- Alle providerclaims zijn geverifieerd tegen officiële bronnen met URL-referentie (§1).
- Geen aannames gebruikt voor kritieke architectuurkeuzes zonder expliciete markering (§7).
- Beslisbomen onderbouwd met laagste-complexiteit/laagste-resourcebelasting-criterium (§2, §3).
- Privacy- en performance-implicaties voor Raspberry Pi 4 zijn vooraf meegenomen in de architectuurkeuzes (§5, §8).
- Geen scope-overschrijding: geen functionaliteit uit opdracht §4 "buiten scope" is meegenomen.

---

## Volgende stap

Fase 2 — Minimale werkende integration, startend met de spike-verificatie van aannames 1 en 2 (§7), gevolgd door manifest, constants, datamodel, providerbase, NDW-provider, API-client, coordinator, config flow, setup/unload, basisentities, translations, basistests en basisdocumentatie — zoals gespecificeerd in opdracht §40.
