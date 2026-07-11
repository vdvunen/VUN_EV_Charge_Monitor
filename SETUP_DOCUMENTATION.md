<!--
Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl
-->

# Setup-documentatie — VUN EV Charge Monitor

## Vereisten

- Home Assistant ≥ 2025.1.0 (zie `hacs.json`; vereist vanwege
  `OptionsFlowWithReload`, `ConfigEntry.runtime_data` en de huidige
  reauth/reconfigure-helpers — zie FASE1-ONDERZOEK-EN-ARCHITECTUUR.md §5).
- Minimaal één Home Assistant-zone (Instellingen → Gebieden & zones → Zones).
- Minimaal één `person`- of `device_tracker`-entiteit.
- Internetverbinding (voor NDW/TomTom/Open Charge Map — niet nodig in
  simulatiemodus).

## Raspberry Pi 4-aandachtspunten

De integratie is expliciet ontworpen voor lage resourcebelasting op een
Raspberry Pi 4 (opdracht §20, FASE1-onderzoek §5):

- Uitsluitend async I/O, geen blocking calls.
- Server-side geografische filtering (bbox bij NDW, radius bij TomTom/OCM) —
  geen landelijke datasets in het geheugen.
- Compacte datamodellen, geen pandas/numpy/GIS-library.
- Geen entity per laadpaal — voorkomt recorder-/registerbelasting.
- Begrensde resultaten (`max_results`) en een verwerkingsplafond per
  providercall.
- Standaard update-interval 5 minuten, instelbaar tussen 1 en 60 minuten.

Verwacht geheugengebruik: enkele MB per config entry (alleen de laatste
gefilterde dataset wordt bewaard, geen historiek). API-verbruik: één
providercall per config entry per update-interval.

## Installatie

### Via HACS (aanbevolen)
1. HACS → Integraties → menu (⋮) → Aangepaste repositories.
2. Voeg toe: `https://github.com/vdvunen/VUN_EV_Charge_Monitor` met categorie "Integratie".
3. Zoek "VUN EV Charge Monitor", installeer, herstart Home Assistant.

### Handmatig
1. Kopieer `custom_components/vun_ev_charge_monitor/` naar de
   `custom_components`-map van je Home Assistant-configuratie.
2. Herstart Home Assistant.

## Providerregistratie en API-keyconfiguratie

| Provider | Registratie nodig? | Waar |
|---|---|---|
| NDW DOT-NL | Nee (bulk/bbox-toegang is publiek) | — |
| TomTom | Ja | https://developer.tomtom.com — maak een app aan, kopieer de API-key |
| Open Charge Map | Ja (gratis) | https://openchargemap.org — Sign in → My Apps → Register An Application |

API-keys worden uitsluitend opgeslagen in de config entry (versleuteld door
Home Assistant's eigen opslag), nooit in platte tekst in logs of
diagnostics.

## Permissies

Geen aanvullende Home Assistant-permissies nodig buiten de standaard
integratiepermissies. De integratie gebruikt uitsluitend de gedeelde
`aiohttp`-sessie van Home Assistant (geen eigen netwerkstack).

## Configuratie

Zie `USER_DOCUMENTATION.md` voor de volledige configuratieflow. Configuratie
verloopt uitsluitend via de UI — geen YAML.

## Teststappen (handmatig, opdracht §38)

1. Installeer de integratie (HACS of handmatig).
2. Herstart Home Assistant.
3. Voeg de integratie toe via de UI.
4. Selecteer een zone.
5. Selecteer een persoon of device tracker.
6. Configureer de provider (test eventueel eerst met simulatiemodus aan).
7. Controleer dat de config flow de providerverbinding test (foutmelding bij
   ongeldige key/geen verbinding).
8. Controleer dat alle entiteiten verschijnen (13 sensoren, 3 binary
   sensors, 2 buttons, 1 event-entiteit).
9. Voer een handmatige refresh uit via de knop.
10. Zet simulatiemodus aan via de opties en controleer de "Sim ..."-locaties.
11. Verplaats de gevolgde persoon/tracker naar de zone via Ontwikkelaarstools
    → Staten, en controleer dat het event `zone_entered` verschijnt.
12. Controleer dat de melding wordt verstuurd (of gebruik de testknop).
13. Verlaat en betreed de zone snel opnieuw — controleer dat de cooldown een
    tweede melding onderdrukt.
14. Zet het notificatiedoel tijdelijk op een niet-bestaande entiteit — er
    hoort een repairmelding "Notificatiedoel ontbreekt" te verschijnen.
15. Verbreek tijdelijk de internetverbinding — controleer `binary_sensor.api_available`
    en dat de laatst bekende data blijft getoond (niet "unavailable").
16. Zet de maximumleeftijd van data laag en wacht — controleer
    `binary_sensor.data_stale`.
17. Herlaad de integratie (Configureren opslaan of "Herladen" in het menu).
18. Verwijder de integratie en voeg opnieuw toe — controleer dat alles
    identiek werkt (idempotent).
19. Voer `get_nearby_chargers` uit via Ontwikkelaarstools → Acties, en
    controleer de servicerespons.
20. Draai de geautomatiseerde testsuite (zie hieronder).

## Geautomatiseerde tests draaien

```bash
python -m venv .venv
# Windows:
.venv\Scripts\pip install -r requirements_test.txt
.venv\Scripts\python -m pytest
# Linux/macOS/WSL:
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

> **Windows-kanttekening:** Home Assistant's testtooling (en HA zelf) is
> alleen officieel ondersteund op Linux/macOS. Op kale Windows-Python botst
> Home Assistant's `ProactorEventLoop`-policy met `pytest-socket`'s
> socketblokkade (`socket.socketpair()`-fallback). Draai de volledige suite
> via WSL2, Docker, of CI (bv. GitHub Actions met een `ubuntu-latest`
> runner) voor een 100% representatieve testrun. Zie `PRODUCTION_CHECK.md`
> voor de exacte stand van de testdekking in deze oplevering.

## Debuglogging

Voeg toe aan `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.vun_ev_charge_monitor: debug
```

Debug-logs bevatten providerrequestcounts, filterresultaten, debounce-/
cooldownbeslissingen — nooit API-keys, coördinaten, notificatiedoelen of
persoonsgegevens (opdracht §22/§23).

## Deployment

Geen aanvullende deploymentstappen — de integratie draait volledig binnen
het bestaande Home Assistant-proces. Geen aparte poorten, containers of
achtergrondprocessen.

## Upgrades

Werk de integratie bij via HACS (of vervang de map handmatig) en herstart
Home Assistant. Config entries blijven behouden; er is nog geen
config-entry-migratie nodig (huidige versie: 1).

## Config entry-migraties

Config entry `version = 1`, geen `minor_version`-migraties tot nu toe. Zodra
een toekomstige wijziging een breaking change vereist, wordt hier een
`async_migrate_entry`-implementatie toegevoegd met bijbehorende
teststappen, foutafhandeling (mislukte migratie beschadigt geen
configuratiegegevens) en rollback-instructies.

## Rollback

Zie `CHANGELOG.md` (rollback-instructie per versie) en `README.md` §
Rollback. Kort samengevat:

1. Schakel de integratie uit / verwijder de config entry (optioneel — data
   blijft behouden bij alleen bestanden vervangen).
2. Verwijder `custom_components/vun_ev_charge_monitor/`.
3. Plaats een eerdere versie terug (of laat weg om volledig te verwijderen).
4. Herstart Home Assistant.
5. Controleer dat er geen restanten (entities, repair issues) achterblijven
   — bij volledige verwijdering via de UI ruimt Home Assistant de entity-
   en device-registryrecords automatisch op.

## Dependencies

Zie `DEPENDENCIES.md` — geen runtime-dependencies, één test-only dependency.

## Troubleshooting

Zie `USER_DOCUMENTATION.md` § Troubleshooting voor gebruikersgerichte
problemen. Voor ontwikkel-/CI-gerelateerde problemen:

- **`ModuleNotFoundError: fcntl` / `resource` tijdens pytest op Windows** —
  bekende Windows-beperking van Home Assistant's testtooling, zie hierboven.
  Gebruik WSL2/Docker/CI.
- **Config flow blijft hangen op "cannot_connect" met simulatiemodus aan** —
  simulatiemodus slaat de providertest bewust over; controleer of het
  simulatiemodus-veld daadwerkelijk is aangevinkt vóór het verzenden van de
  eerste stap.
