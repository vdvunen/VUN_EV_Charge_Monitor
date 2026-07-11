<!--
Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl
-->

# VUN EV Charge Monitor

Home Assistant custom integration die actuele informatie over openbare
laadpunten rond een Home Assistant-zone ophaalt, filtert en toont, en een
melding stuurt zodra een gevolgde persoon of device tracker die zone
binnenkomt.

> **Status:** v1.0.0 — alle fases (1 t/m 6) opgeleverd. Zie
> `FASE1-ONDERZOEK-EN-ARCHITECTUUR.md`, `CHANGELOG.md` en
> `PRODUCTION_CHECK.md` voor de volledige projectgeschiedenis, gemaakte
> keuzes en openstaande verificatiepunten.

## Projectomschrijving

Vind, filter en volg openbare EV-laadpunten in de buurt van een Home
Assistant-zone, volledig lokaal — geen aparte service, container of
cloudbackend. Wanneer een gevolgd gezinslid of device de zone binnenkomt,
stuurt Home Assistant automatisch een overzicht van de beste laadopties in
de buurt.

## Features

- Zoekt laadlocaties binnen een configureerbare radius rond een bestaande
  Home Assistant-zone.
- Drie providers: **NDW DOT-NL** (primair, gratis, Nederland),
  **TomTom** (bring-your-own-key, per-aansluiting-status) en
  **Open Charge Map** (bring-your-own-key, statische fallback).
- Filtert op connectortype, minimaal laadvermogen en (optioneel) uitgesloten
  operators; sorteert op beschikbaarheid, afstand, vermogen en actualiteit —
  zonder ingebouwde merkvoorkeur.
- Optioneel: echte rijafstand i.p.v. hemelsbreed voor de topresultaten, via
  een gratis OpenRouteService-key (bring-your-own-key, begrensd tot de
  top-5 kandidaten om het API-verbruik laag te houden).
- 13 sensoren, 3 binary sensors, 2 buttons en 1 event-entiteit — zie
  `USER_DOCUMENTATION.md` voor het volledige overzicht.
- Automatische zone-entrydetectie met debounce, cooldown en deduplicatie.
- Drie meldingvarianten (beschikbaar / niets beschikbaar / alleen
  statische data), in het Nederlands en Engels.
- Simulatiemodus voor testen zonder echte API-calls.
- Volledig configureerbaar via de UI (config flow + options flow),
  inclusief reauth- en reconfigure-flow.
- Diagnostics met volledige redactie van gevoelige gegevens; repairs bij
  verwijderde zone/entity, ontbrekend notificatiedoel of langdurig
  onbereikbare provider.
- Service `get_nearby_chargers` voor gebruik in eigen scripts/automations.

## Architectuur

```
custom_components/vun_ev_charge_monitor/
├── __init__.py            setup/unload-lifecycle, providerfactory
├── api.py                 generieke HTTP-client (retries/back-off/429)
├── binary_sensor.py
├── button.py               vernieuwen + testmelding
├── config_flow.py          config- en optionsflow
├── const.py
├── coordinator.py          DataUpdateCoordinator
├── diagnostics.py
├── entity.py                gedeelde basisentiteit/device
├── event.py
├── manifest.json
├── models.py                intern, provideronafhankelijk datamodel
├── notifications.py          meldingtekst + verzending
├── repairs.py
├── sensor.py
├── services.py / services.yaml
├── strings.json / translations/
├── zone_tracking.py           person/device_tracker-listeners
└── providers/
    ├── _common.py            gedeelde normalisatiehelpers
    ├── base.py                providercontract
    ├── ndw.py                 NDW DOT-NL
    ├── tomtom.py               TomTom EV Search
    ├── open_charge_map.py       Open Charge Map
    └── simulation.py            lokale testdata
```

Zie `FASE1-ONDERZOEK-EN-ARCHITECTUUR.md` voor de volledige onderbouwing van
alle architectuurkeuzes (providerkeuze, statusnormalisatie, HA-patronen).

## Ondersteunde providers

| Provider | API-key | Realtime | Dekking |
|---|---|---|---|
| NDW DOT-NL | Niet nodig | Ja (geaggregeerd per connectortype) | Nederland |
| TomTom | Vereist (eigen) | Ja (per aansluiting) | Wereldwijd |
| Open Charge Map | Vereist (gratis) | Nee — alleen locatiedata | Wereldwijd |

## Installatie

### Via HACS (custom repository)
1. HACS → Integraties → menu (⋮) → Aangepaste repositories.
2. Voeg toe: `https://github.com/vdvunen/VUN_EV_Charge_Monitor` met categorie "Integratie".
3. Installeer "VUN EV Charge Monitor" en herstart Home Assistant.
4. Voeg de integratie toe via **Instellingen → Apparaten & diensten**.

### Handmatig
1. Kopieer `custom_components/vun_ev_charge_monitor/` naar de
   `custom_components`-map van je Home Assistant-installatie.
2. Herstart Home Assistant.
3. Voeg de integratie toe via **Instellingen → Apparaten & diensten →
   Integratie toevoegen** en zoek naar "VUN EV Charge Monitor".

Zie `SETUP_DOCUMENTATION.md` voor de volledige installatie-, configuratie-
en teststappen.

## Configuratie

Vier stappen: zone + provider, gevolgde personen/trackers, zoekopties,
notificaties. Alle instellingen zijn achteraf aanpasbaar via
**Configureren**. Volledige details in `USER_DOCUMENTATION.md`.

## Entities

13 sensoren (o.a. beschikbare laadlocaties/aansluitingen, beste locatie met
afstand/vermogen/operator/adres/navigatielink, API-status), 3 binary
sensors (laadlocatie beschikbaar, API beschikbaar, data verouderd), 2
buttons (vernieuwen, testmelding), 1 event-entiteit, en tot `max_results`
kaartmarker-entiteiten (`geo_location`) — rood/oranje/groen op basis van
beschikbaarheid, direct bruikbaar in een `map`-kaart. Zie
`USER_DOCUMENTATION.md` voor het volledige overzicht en welke sensoren
standaard uitgeschakeld zijn.

## Events

`zone_entered`, `availability_changed`, `charger_available`,
`provider_unavailable` — bruikbaar als trigger in eigen automatiseringen.

## Services

`vun_ev_charge_monitor.get_nearby_chargers` — geeft de actuele topresultaten
terug voor een config entry (service response), zonder ruwe providerdata of
gevoelige configuratie prijs te geven.

## Notificaties

Automatische melding bij zone-entry, met drie varianten afhankelijk van de
actuele data (beschikbaar / niets beschikbaar / alleen statische data), in
het Nederlands of Engels. Zie `USER_DOCUMENTATION.md` voor voorbeeldteksten.

## Privacy

Verwerkt de actuele status van geselecteerde `person`-/`device_tracker`-
entiteiten, uitsluitend voor zone-entrydetectie. Geen opslag van
bewegingshistorie. Diagnostics redacteren API-keys, zone, gevolgde
entiteiten en notificatiedoel volledig. Zie `USER_DOCUMENTATION.md` §
Privacy.

## Beperkingen

- Geen starten/stoppen van laadsessies, reserveren, betalen of volledige
  routeplanning (buiten scope, zie opdracht).
- Open Charge Map levert nooit actuele bezetting.
- NDW's per-aansluiting-status is een gedocumenteerde, best-effort
  benadering op basis van geaggregeerde tellingen.
- Zie `PRODUCTION_CHECK.md` voor de volledige, eerlijke stand van
  testdekking en openstaande verificatiepunten.

## Troubleshooting

Zie `USER_DOCUMENTATION.md` § Veelvoorkomende fouten en § Troubleshooting,
en `SETUP_DOCUMENTATION.md` § Troubleshooting voor ontwikkel-/CI-gerelateerde
problemen.

## Versiebeheer

Semantic Versioning — zie `CHANGELOG.md` voor de volledige historie inclusief
rollback-instructies per versie.

## Licentie

MIT — zie `LICENSE`.

## Credits

Developed by Vincent van Unen — https://www.unen.nl — code@unen.nl

Databronnen: [NDW](https://www.ndw.nu/), [TomTom](https://developer.tomtom.com/),
[Open Charge Map](https://openchargemap.org/).
