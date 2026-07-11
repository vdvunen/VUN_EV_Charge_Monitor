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

## Providers (Fase 5, afgerond)

TomTom en Open Charge Map zijn geïmplementeerd zonder extra runtime-
dependency, zoals voorzien: beide bronnen leveren JSON via HTTP, verwerkt
met de standaardbibliotheek en de reeds aanwezige `ApiClient` (`api.py`) en
gedeelde normalisatiehelpers (`providers/_common.py`).
