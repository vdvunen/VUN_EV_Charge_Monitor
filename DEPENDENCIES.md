<!--
Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl
-->

# Dependencies — VUN EV Charge Monitor

## Runtime dependencies

**Geen.** De integration draait volledig op de Home Assistant/Python-standaardbibliotheek:

- `aiohttp` — al aanwezig via Home Assistant's gedeelde HTTP-sessie (`homeassistant.helpers.aiohttp_client`), geen eigen requirement.
- `homeassistant.util.location` — native afstandsberekening, geen GIS-library nodig.
- `json`, `math`, `dataclasses`, `enum` — Python-standaardbibliotheek.

`manifest.json` → `"requirements": []`.

Deze keuze is direct onderbouwd in FASE1-ONDERZOEK-EN-ARCHITECTUUR.md §5/§10 (opdracht §20/§32: geen dependency toevoegen wanneer native functionaliteit voldoet).

## Test-dependencies

| Naam | Versie | Doel | Reden | Native alternatief overwogen | Security-/onderhoudsrisico | Performance-impact |
|---|---|---|---|---|---|---|
| `pytest-homeassistant-custom-component` | `0.13.345` (gepind in `requirements_test.txt`) | Testutilities voor custom_components (`MockConfigEntry`, HA-test-fixtures) | Spiegelt de officiële HA-core testinfrastructuur; dagelijks bijgewerkt tegen de laatste HA-release | Eigen test-fixtures bouwen bovenop kale `pytest` | Laag — uitsluitend dev-/CI-dependency, geen productie-impact; community-onderhouden, actieve releasecadans | Geen (draait niet op de Raspberry Pi 4 productieomgeving) |

Geen overige test-dependencies nodig; `pytest-asyncio` en overige testtooling worden als transitieve dependency meegeleverd door `pytest-homeassistant-custom-component`.

`pyflakes` is tijdens de Fase 6-reviewpass eenmalig los geïnstalleerd voor statische analyse (onbevestigde imports/dead code). Dit is een ontwikkeltool, niet toegevoegd aan `requirements_test.txt` — geen doorlopende CI-dependency, puur gebruikt als eenmalige controle tijdens deze oplevering.

`python-docx` en `Pillow` zijn eveneens eenmalig los geïnstalleerd, respectievelijk voor het genereren van `User_Documentation.docx` (Fase 6) en de PNG-assets (`brand/icon.png`/`icon@2x.png`, en de rood/oranje/groen kaartmarkers in `markers/`). Beide zijn documentatie-/asset-generatietools, niet opgenomen in `requirements_test.txt` of `manifest.json` — de gegenereerde output (het `.docx`-bestand, de PNG's) is wat wordt opgeleverd, niet de tool zelf. De marker-PNG's worden op runtime uitsluitend gelezen en statisch geserveerd (`hass.http.async_register_static_paths`), niet gegenereerd — geen Pillow-afhankelijkheid in `manifest.json`.

## Providers (Fase 5, afgerond)

TomTom en Open Charge Map zijn geïmplementeerd zonder extra runtime-
dependency, zoals voorzien: beide bronnen leveren JSON via HTTP, verwerkt
met de standaardbibliotheek en de reeds aanwezige `ApiClient` (`api.py`) en
gedeelde normalisatiehelpers (`providers/_common.py`).

## Rijafstand-verrijking (OpenRouteService)

Ook geen nieuwe runtime-dependency. `distance.py` hergebruikt `ApiClient`
(nu uitgebreid met POST-ondersteuning voor de OpenRouteService Matrix API)
en levert JSON via HTTP, net als de bestaande providers. Optioneel en
bring-your-own-key — zonder geconfigureerde OpenRouteService-key blijft de
hemelsbrede (Haversine) afstand de standaard, zonder enige externe call.

## Routegebaseerd zoeken (OpenRouteService)

Eveneens geen nieuwe runtime-dependency. `route.py` hergebruikt dezelfde
`ApiClient` en dezelfde OpenRouteService-key, maar spreekt de Directions API
aan (`format=geojson`) i.p.v. de Matrix API. Optioneel en bring-your-own-key
— zonder geconfigureerde bestemmingszone blijft het bestaande straal-
zoekgedrag ongewijzigd, zonder enige externe call.
