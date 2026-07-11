<!--
Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl
-->

# Production Check — VUN EV Charge Monitor v1.0.0

Eerlijke stand van zaken per controlepunt (opdracht §41 productiecheck).
Waar iets niet (volledig) geverifieerd kon worden, staat dat expliciet
vermeld — geen valse "alles groen"-claims.

## Security

- [x] Geen secrets in broncode; API-keys uitsluitend in config entries.
- [x] API-keys geredacteerd in diagnostics (`diagnostics.py TO_REDACT`).
- [x] API-keys nooit gelogd — expliciet geverifieerd tijdens de Fase
      6-reviewpass; een concreet lek (aiohttp `ContentTypeError` die de
      volledige requeststring incl. querystring embedt, relevant voor
      TomTom's key-als-queryparameter) is gevonden en gefixt door nergens
      meer ruwe externe exceptieteksten in eigen foutmeldingen over te
      nemen (zie `api.py::_safe_exc_text`).
- [x] HTTPS afgedwongen op alle drie providers, hardcoded allowlist-URL's,
      geen door de gebruiker vrij in te voeren endpoint (SSRF-bescherming).
- [x] Geen shellcommands, geen `eval`/dynamische code-executie, geen
      willekeurige bestandstoegang.
- [x] Veilige time-outs en begrensde retries op elke providercall.
- [x] Input sanitization: alle providerresponses worden defensief
      gevalideerd (type-checks, ongeldige records genegeerd i.p.v. crash).

## Privacy

- [x] Geen persoonsgegevens/coördinaten/bewegingshistorie op info-niveau
      gelogd (alleen entity_id's op debug-niveau bij zone-entrydetectie).
- [x] Geen persistente opslag van trackingdata — alleen een in-memory
      cooldown-tijdstempel per config entry.
- [x] Notificatiedoel, zone en gevolgde entiteiten volledig geredacteerd in
      diagnostics.

## Performance

- [x] Volledig async I/O, geen blocking calls.
- [x] Server-side geografische filtering waar mogelijk (NDW bbox, TomTom/OCM
      radius-parameter).
- [x] Compacte datamodellen (frozen dataclasses/slots), geen pandas/numpy.
- [x] Geen entity per laadpaal — voorkomt recorder-/registerbelasting.
- [x] Begrensde resultaten en een verwerkingsplafond per providercall.

## Logging

- [x] Debug/info/warning/error correct gescheiden per opdracht §23.
- [x] Info-niveau beperkt tot succesvolle setup + providerselectie.

## Error handling

- [x] Alle providerfouten vertaald naar een klein, consistent set interne
      excepties (`ProviderAuthError`/`RateLimitedError`/`ConnectionError`/
      `ResponseError`), afgehandeld door de coordinator.
- [x] `ConfigEntryAuthFailed` triggert automatisch de HA-reauth-flow.
- [x] Ongeldige/onvolledige providerrecords worden overgeslagen, niet
      fataal.

## Retries / rate limits

- [x] Exponentiële back-off, begrensd aantal retries, HTTP 429 +
      `Retry-After` gerespecteerd zonder agressieve retrylus.

## Idempotency

- [x] `async_setup_entry`/`async_unload_entry` idempotent; herhaald
      opzetten/ontladen laat geen dubbele listeners/services achter
      (`services.py` registreert idempotent via `has_service`-check,
      `ZoneEntryTracker.async_unload()` is veilig dubbel aanroepbaar).
- [x] Repair-issues worden bij unload/verwijdering van de config entry
      volledig opgeruimd (`repairs.async_clear_all_issues_for_entry`) —
      gevonden en gefixt tijdens de Fase 6-reviewpass (was eerder een gat).

## Unload / reload

- [x] Platforms, coordinator en zone-tracker-listeners worden volledig
      opgeruimd bij unload.
- [x] Reload verloopt via `OptionsFlowWithReload` (opties) of Home
      Assistant's standaard reload-actie — geen handmatige listener nodig.

## Migrations

- [x] Config entry `version = 1`, nog geen migratie nodig. Migratiepad
      gedocumenteerd in `SETUP_DOCUMENTATION.md` voor toekomstig gebruik.

## Inputvalidatie / responsevalidatie

- [x] Config flow valideert zone, entities, radius, interval,
      notificatiedoel vóór opslag; ongeldige configuratie wordt nooit
      opgeslagen.
- [x] Providerresponses worden veldsgewijs gevalideerd (type- en
      bereikcontroles) vóór normalisatie naar het interne model.

## Stale data

- [x] `CoordinatorData.is_stale()` + `binary_sensor.data_stale` +
      diagnostics-veld `is_stale`. Laatst geldige data blijft zichtbaar bij
      een tijdelijke providerfout (opdracht §19).

## Diagnostics

- [x] Volledig geïmplementeerd met redactie, zie `diagnostics.py`.

## Repairs

- [x] Vier scenario's geïmplementeerd: zone verwijderd, gevolgde entiteit
      verwijderd, provider langdurig onbereikbaar, notificatiedoel
      ontbreekt.

## Tests

**Geschreven:** volledige set (11 testmodules, opdracht §29-lijst gedekt
plus `test_services.py`).

**Uitgevoerd en groen in déze ontwikkelomgeving (Windows, native Python,
geen WSL/Docker beschikbaar):**
- `test_models.py` — 5/5 PASSED.
- `test_api.py` — 8/8 PASSED.
- Provider-normalisatielogica (NDW/TomTom/Open Charge Map) — geverifieerd
  via losse scripts tegen de echte fixtures (identieke assertions als in
  `test_providers.py`), niet via pytest zelf.
- Notificatie-berichtopbouw (alle 3 varianten × NL/EN) — geverifieerd via
  een los script, output vergeleken met de exacte voorbeeldteksten uit
  opdracht §3 (100% match, inclusief NL-decimaalnotatie).
- Zone-entrytransitielogica (`_is_zone_entry`) — geverifieerd via een los
  script (6 scenario's).

**Niet uitvoerbaar via pytest in déze omgeving:** alle tests die de `hass`-
fixture nodig hebben (`test_coordinator.py`, `test_config_flow.py`,
`test_init.py`, `test_unload.py`, `test_diagnostics.py`, `test_sensors.py`,
`test_zone_tracking.py`, `test_services.py`, de fixture-afhankelijke delen
van `test_providers.py`). Oorzaak: Home Assistant's Windows-
`ProactorEventLoop`-policy botst met `pytest-socket`'s blokkade van
`socket.socketpair()` — een bekende omgevingsbeperking van
`pytest-homeassistant-custom-component` op kale Windows-Python, geen
codefout. Indirect bewijs van correctheid: alle 22 productiemodules
importeren foutloos tegen een echt geïnstalleerde Home Assistant-package
(inclusief na de reviewpass-fixes), en `pyflakes` rapporteert nul
problemen over de volledige `custom_components/`- en `tests/`-boom.

**Aanbeveling:** draai de volledige suite in WSL2, Docker, of CI (Linux-
runner) vóór een eventuele publicatie naar HACS default — dit is
standaardpraktijk voor Home Assistant custom-component-ontwikkeling en
geen bijzonderheid van dit project.

## Documentatie

- [x] Volledige set aanwezig (zie bestandenoverzicht in README.md).

## Rollback

- [x] Rollback-instructies aanwezig in `CHANGELOG.md` (per versie) en
      `README.md`/`SETUP_DOCUMENTATION.md`.

## HACS-validatie

- [x] `hacs.json` met verplicht `name`-veld aanwezig.
- [x] `manifest.json` bevat alle verplichte velden (`domain`, `name`,
      `codeowners`, `documentation`, `issue_tracker`, `requirements`,
      `version`, `integration_type`, `iot_class`).
- [x] `codeowners`/`documentation`/`issue_tracker` verwijzen naar de echte,
      publieke repository: https://github.com/vdvunen/VUN_EV_Charge_Monitor
- [ ] **Niet geverifieerd:** de daadwerkelijke HACS-validatieactie zelf
      (HACS' eigen linting/validation-workflow tegen de live repository) is
      in deze sessie niet uitgevoerd — vereist een GitHub Actions-run op de
      repository. Aanbevolen als eerste CI-stap na deze oplevering.

## Home Assistant-validatie

- [x] Alle geïmporteerde HA-APIs (selectors, `DataUpdateCoordinator`,
      `ConfigEntry.runtime_data`, `OptionsFlowWithReload`, `EventEntity`,
      reauth/reconfigure-helpers) zijn geverifieerd tegen een echt
      geïnstalleerde, actuele Home Assistant-package — geen aannames uit
      trainingsdata.
- [ ] **Niet uitgevoerd:** de officiële `hassfest`-validatietool (onderdeel
      van HA-core se CI) — vereist een volledige core-checkout, buiten
      scope van deze sessie. Aanbevolen als CI-stap bij publicatie.

## Openstaande, expliciet gemarkeerde aannames (zie ook FASE1-onderzoek §7)

1. Authenticatiemechanisme van de live NDW-API (`dotnl.ndw.nu`) — nooit
   getest tegen een echte respons (geen testomgeving met live NDW-toegang
   beschikbaar). Code ondersteunt zowel met als zonder key.
2. NDW's exacte per-EVSE statusgranulariteit — bevestigd is alleen
   geaggregeerd `available`/`total`; de synthetische EVSE-constructie in
   `providers/ndw.py` is een gedocumenteerde, redelijke benadering.

Geen van beide blokkeert normaal gebruik; beide zijn aanbevolen
verificatiepunten voor een toekomstige patch-release zodra live
NDW-toegang beschikbaar is.
