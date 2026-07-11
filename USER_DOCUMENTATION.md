<!--
Developed by Vincent van Unen
Website: https://www.unen.nl
Email: code@unen.nl
-->

# Gebruikersdocumentatie — VUN EV Charge Monitor

## Functionaliteit

VUN EV Charge Monitor zoekt openbare laadpunten rond een Home Assistant-zone,
toont de actuele beschikbaarheid via entiteiten, en stuurt (optioneel) een
melding zodra een gevolgde persoon of device tracker die zone binnenkomt.

De integratie draait volledig lokaal binnen Home Assistant — geen aparte
service, container of cloudbackend nodig.

## Dagelijks gebruik

Na installatie en configuratie werkt de integratie op de achtergrond:

1. De coordinator haalt periodiek (standaard elke 5 minuten) actuele
   laadpuntdata op binnen de ingestelde radius rond je zone.
2. De sensoren tonen altijd de meest recente, gefilterde en gesorteerde data.
3. Komt een gevolgde persoon/tracker de zone binnen, dan ontvang je (indien
   ingeschakeld) automatisch een melding met de beste laadopties.
4. Je kunt op elk moment handmatig vernieuwen via de **Vernieuwen**-knop, of
   een testmelding versturen via **Testmelding versturen**.

## Configuratie

Voeg de integratie toe via **Instellingen → Apparaten & diensten → Integratie
toevoegen → VUN EV Charge Monitor**. De configuratie doorloopt vier stappen:

### 1. Zone en provider
- **Zone**: een bestaande Home Assistant-zone als zoekmiddelpunt.
- **Provider**: de databron.
  - **NDW DOT-NL** — officiële Nederlandse open dataset, werkt zonder key.
  - **TomTom** — vereist je eigen TomTom-API-key, levert per-aansluiting-status.
  - **Open Charge Map** — vereist een gratis API-key, uitsluitend statische
    locatiedata (geen actuele bezetting).
- **API-key**: optioneel/verplicht afhankelijk van de gekozen provider.
- **Simulatiemodus**: gebruikt lokale testdata, geen echte API-calls (zie
  onder).

### 2. Gevolgde personen en apparaten
Selecteer minimaal één `person`- en/of `device_tracker`-entiteit. Zodra een
van deze de gekozen zone binnenkomt, wordt (indien ingeschakeld) een melding
verstuurd.

### 3. Zoekopties
- Zoekradius (of de radius van de zone zelf gebruiken).
- Maximaal aantal resultaten.
- Connectortypen (leeg = alle).
- Minimaal laadvermogen.
- Update-interval.
- Maximumleeftijd van data (waarna deze als "verouderd" wordt gemarkeerd).

### 4. Notificaties
- Notificatiedoel (een `notify`-entiteit, apparaat, gebied of label).
- Melding bij zone-entry aan/uit.
- Melding bij wijziging beschikbaarheid aan/uit.
- Cooldown tussen meldingen (minuten).
- Taal van de melding (Nederlands/Engels).

Alle instellingen zijn achteraf aanpasbaar via **Configureren** op de
integratietegel.

## Sensoren

| Sensor | Beschrijving |
|---|---|
| Beschikbare laadlocaties | Aantal locaties met minimaal één vrije aansluiting |
| Beschikbare aansluitingen | Totaal aantal vrije aansluitingen over alle locaties |
| Totaal aantal laadlocaties *(standaard uit)* | Alle gevonden locaties, ongeacht beschikbaarheid |
| Totaal aantal aansluitingen *(standaard uit)* | Alle aansluitingen over alle locaties |
| Beste laadlocatie | Naam van de best gesorteerde locatie |
| Afstand tot beste locatie | In meters |
| Max. vermogen beste locatie | In kW |
| Operator beste locatie *(standaard uit)* | |
| Adres beste locatie *(standaard uit)* | |
| Navigatielink *(standaard uit)* | Google Maps-link naar de beste locatie |
| Laatste succesvolle update | Tijdstip van de laatst gelukte databevraging |
| Databron *(standaard uit)* | Naam van de actieve provider |
| API-status | `ok`, `cannot_connect`, `invalid_auth`, `rate_limited` of `unknown` |

De sensor "Beschikbare laadlocaties" heeft een attribuut `top_locations` met
een compacte lijst (max. 5) van naam, afstand, beschikbaarheid en vermogen —
handig voor eigen dashboardkaarten of automatiseringen.

Standaard uitgeschakelde sensoren kun je alsnog activeren via de
entiteiteninstellingen.

## Binary sensors

| Binary sensor | Aan wanneer... |
|---|---|
| Laadlocatie beschikbaar | Minimaal één locatie binnen de radius vrij is |
| API beschikbaar | De laatste providercall succesvol was |
| Data verouderd | De laatst opgehaalde data ouder is dan de ingestelde maximumleeftijd |

## Button

- **Vernieuwen** — forceert direct een nieuwe databevraging.
- **Testmelding versturen** — verstuurt direct een melding met de huidige
  data, zonder rekening te houden met de cooldown of de zone-entry-toggle.

## Events

De event-entiteit **Activiteit** signaleert:

- `zone_entered` — een gevolgde persoon/tracker is de zone binnengekomen.
- `availability_changed` — het aantal beschikbare aansluitingen is gewijzigd.
- `charger_available` — er kwam een aansluiting beschikbaar terwijl er
  daarvoor nul beschikbaar waren.
- `provider_unavailable` — de provider is meerdere pogingen achtereen
  onbereikbaar.

Deze events zijn bruikbaar als trigger in eigen automatiseringen, los van de
ingebouwde notificatielogica.

## Notificaties

Bij een zone-entry (of via de testknop) ontvang je één van drie
berichtvarianten, afhankelijk van de actuele data:

**Beschikbare laadpunten:**
```
Laadpunten in de buurt van Woonwijk

Er zijn 3 laadlocaties met in totaal 7 vrije aansluitingen.

1. P+R Centrum
   3 van 6 beschikbaar
   Type 2 · maximaal 22 kW
   280 meter afstand

...

Bijgewerkt om 16:32 via NDW DOT-NL.
```

**Geen beschikbare laadpunten:**
```
Er zijn momenteel geen vrije laadpunten binnen 1,5 kilometer van Woonwijk.

De status is voor het laatst bijgewerkt om 16:32.
```

**Alleen statische data (bv. bij Open Charge Map):**
```
Er zijn 5 laadlocaties gevonden, maar de actuele bezetting is niet beschikbaar.

Controleer voor vertrek de laadpaalapp voordat je de laadkabel alvast
enthousiast uit de kofferbak haalt.
```

## Filters

- **Connectortypen**: beperk resultaten tot Type 2, CCS, CHAdeMO, Type 1 of
  huishoudstekker. Leeg = alle typen.
- **Minimaal vermogen**: verberg locaties onder een ingesteld kW-vermogen.
- **Zoekradius**: eigen radius, of de radius van de gekozen zone.

## Navigatielinks

Elke laadlocatie krijgt een kant-en-klare Google Maps-navigatielink
(`sensor.navigation_url` en in elke serviceresponse).

## Simulatiemodus

Schakel simulatiemodus in tijdens het toevoegen of via de opties om de
integratie te testen zonder echte API-calls. Simulatiemodus levert drie
vaste testlocaties met verschillende beschikbaarheid (deels beschikbaar,
volledig bezet, hoog vermogen beschikbaar) rond je zone, duidelijk herkenbaar
aan de naam ("Sim ...") en de databron "Simulatie".

Handig om:
- de notificatietekst te controleren (testknop);
- stale-databehandeling te testen (zet de maximumleeftijd laag en wacht);
- zone-entrygedrag te testen (verplaats de gevolgde persoon/tracker via
  Ontwikkelaarstools naar de zone).

## Veelvoorkomende fouten

| Foutcode | Betekenis | Oplossing |
|---|---|---|
| `invalid_zone` | Zone niet gevonden of ongeldige coördinaten | Kies een bestaande zone met geldige latitude/longitude |
| `invalid_entity` | Geen geldige persoon/tracker geselecteerd | Selecteer minimaal één bestaande entiteit |
| `cannot_connect` | Provider niet bereikbaar | Controleer je internetverbinding |
| `invalid_auth` | API-key geweigerd of ontbreekt | Controleer de API-key (verplicht voor TomTom/Open Charge Map) |
| `rate_limited` | Provider limiteert het aantal aanvragen | Probeer het later opnieuw, verlaag de update-frequentie |
| `invalid_notification_service` | Notificatiedoel niet gevonden | Kies een geldig notificatiedoel |

## Beperkingen

- Geen starten/stoppen van laadsessies, reserveren of betalen.
- Geen volledige routeplanning (wel een externe navigatielink).
- Open Charge Map levert nooit actuele bezetting, alleen locatiegegevens.
- NDW's per-aansluiting-status is een best-effort benadering op basis van
  geaggregeerde tellingen (zie `providers/ndw.py`).

## Privacy

De integratie verwerkt de status van de door jou geselecteerde `person`- en
`device_tracker`-entiteiten, uitsluitend om zone-entry te detecteren. Er
wordt geen bewegingshistorie opgeslagen — alleen het moment van de laatst
gedetecteerde zone-entry (in het geheugen, niet op schijf). Diagnostics
redacteren de gekozen zone, gevolgde entiteiten, API-key en notificatiedoel
volledig.

## Troubleshooting

1. **Geen data?** Controleer de sensor "API-status" en binary sensor "API
   beschikbaar". Bekijk de Home Assistant-log op `warning`/`error`-niveau.
2. **Verouderde data?** Controleer binary sensor "Data verouderd" en verhoog
   zo nodig de maximumleeftijd of verlaag het update-interval.
3. **Geen melding ontvangen?** Controleer of "Melding bij binnenkomst zone"
   aan staat, of de cooldown nog actief is, en of het notificatiedoel nog
   bestaat (zie eventuele repair-melding "Notificatiedoel ontbreekt").
4. **Debug-logging inschakelen**: voeg toe aan `configuration.yaml`:
   ```yaml
   logger:
     logs:
       custom_components.vun_ev_charge_monitor: debug
   ```
