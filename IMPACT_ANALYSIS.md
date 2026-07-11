<!--
Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl
-->

# Impact Analysis — VUN EV Charge Monitor v1.0.0

## Bestanden

Greenfield project — geen bestaande Home Assistant-configuratie of
bestanden geraakt. Nieuwe map: `custom_components/vun_ev_charge_monitor/`
(22 Python-modules + manifest/strings/translations), plus projectbestanden
op root-niveau (documentatie, `hacs.json`, `pyproject.toml`, `LICENSE`,
tests).

## Configuratie

Uitsluitend via de Home Assistant-UI (config entries), geen wijzigingen aan
`configuration.yaml` vereist (optioneel: debug-logging toevoegen). Elke
config entry is volledig onafhankelijk — meerdere zones/config entries
beïnvloeden elkaar niet (geen gedeelde globale state, zie
`ConfigEntry.runtime_data`-patroon).

## Dependencies

Geen nieuwe runtime-dependencies. Eén dev-/test-only dependency
(`pytest-homeassistant-custom-component`), zonder productie-impact. Zie
`DEPENDENCIES.md`.

## API-koppelingen

Drie externe HTTPS-API's, elk optioneel/onafhankelijk activeerbaar per
config entry:
- NDW DOT-NL (geen key, Nederlandse publieke dataset).
- TomTom EV Search (bring-your-own-key, wereldwijd).
- Open Charge Map (bring-your-own-key, statische fallback).

Alle drie zijn allowlisted, hardcoded HTTPS-endpoints — geen
gebruikersinvoer voor het endpoint zelf (SSRF-bescherming). Netwerkverkeer
is begrensd tot één call per config entry per update-interval (standaard 5
minuten), plus incidentele calls bij handmatige refresh of config-
flowvalidatie.

## Authenticatie

API-keys (indien van toepassing) worden uitsluitend opgeslagen in de
config entry-data van Home Assistant's eigen encrypted storage. Nooit
gelogd, nooit in platte tekst in diagnostics (volledige redactie via
`async_redact_data`). Reauth-flow triggert automatisch bij HTTP 401/403.

## Logging

Nieuwe logger-namespace `custom_components.vun_ev_charge_monitor` (en
submodules). Standaard stil op info-niveau behalve bij setup/provider-
selectie; debug-niveau desgewenst inschakelbaar. Geen persoonsgegevens,
coördinaten of secrets in enig logniveau (expliciet geverifieerd tijdens de
Fase 6-reviewpass, zie `PRODUCTION_CHECK.md`).

## Privacy

De integratie verwerkt de actuele status (niet de geschiedenis) van door de
gebruiker geselecteerde `person`-/`device_tracker`-entiteiten, uitsluitend
om zone-entry te detecteren. Geen persistente opslag van bewegingsdata —
alleen een in-memory tijdstempel van de laatst verwerkte zone-entry per
config entry (verdwijnt bij herstart). Zie `USER_DOCUMENTATION.md` §
Privacy voor de gebruikersgerichte uitleg.

## Documentatie

Volledige set opgeleverd: `README.md`, `USER_DOCUMENTATION.md`,
`SETUP_DOCUMENTATION.md`, `User_Documentation.docx`, `CHANGELOG.md`,
`DEPENDENCIES.md`, `IMPACT_ANALYSIS.md` (dit bestand),
`PRODUCTION_CHECK.md`, `FASE1-ONDERZOEK-EN-ARCHITECTUUR.md`.

## Deployment

Geen wijziging aan de Home Assistant-deploymentwijze — draait binnen het
bestaande HA-proces op de Raspberry Pi 4 (of elke andere HA-hostomgeving).
Geen extra poorten, containers, of achtergrondprocessen.

## Gebruikersimpact

Positief: automatische, actuele laadpuntinformatie zonder handmatig een
aparte app te hoeven raadplegen, met optionele proactieve meldingen bij
thuiskomst/zonebinnenkomst. Geen breaking impact op bestaande
functionaliteit — dit is een nieuwe, op zichzelf staande integratie.

## Home Assistant Recorder

Bewust geen entity per laadpaal (opdracht §17/§20) — voorkomt onnodige
recorder-/databasebelasting. Alleen de ~19 entry-brede entiteiten worden
gehistoriseerd door de recorder, met compacte state-attributen (max. 5
records in `top_locations`, geen geneste ruwe providerdata).

## Raspberry Pi 4-resources

Zie `SETUP_DOCUMENTATION.md` § Raspberry Pi 4-aandachtspunten. Samengevat:
laag geheugengebruik (enkele MB per config entry), laag CPU-gebruik (async
I/O, geen zware berekeningen), begrensd netwerkverkeer (server-side
gefilterde, kleine JSON-responses).
