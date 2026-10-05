# Voorbeeldautomatiseringen

Vervang voorbeeld-entiteiten en notify-acties door de waarden van jouw
installatie. Sinds 0.7 werkt een gebeurtenis per pakket meestal beter voor
een persoonlijke melding dan een teller die van 0 naar 1 gaat: de gebeurtenis
bevat de vervoerder en wordt per statusovergang verstuurd. De eerste scan na
de upgrade meldt bestaande pakketten niet opnieuw.

De dagelijkse ontvangstbevestiging is iets anders dan een melding zodra een
vervoerder een pakket aanmeldt. Maak daarvoor de automatisering hieronder.
Een mail met alleen de status `registered` of `in_transit` verhoogt de teller
voor **vandaag onderweg** nog niet.

## Melding bij een nieuw pakket

```yaml
alias: Nieuw pakket gemeld
triggers:
  - trigger: event
    event_type: pakket_tracker_parcel_registered
actions:
  - action: notify.mobile_app_telefoon
    data:
      title: "📦 Nieuw pakket"
      message: "{{ trigger.event.data.carrier or 'Een vervoerder' }} heeft een pakket gemeld."
mode: queued
```

## Melding bij een probleemstatus

```yaml
alias: Pakket probleem melden
triggers:
  - trigger: numeric_state
    entity_id: sensor.pakket_tracker_problemen
    above: 0
actions:
  - action: notify.mobile_app_telefoon
    data:
      title: "📦 Pakketprobleem"
      message: "Er is een pakket met een probleemstatus. Controleer Pakket Tracker."
mode: single
```

## Dagelijkse bevestiging

De dagelijkse ontvangstbevestiging wordt niet via een automation-service
gestuurd. Schakel in de configuratie-opties van Pakket Tracker
`Dagelijkse ontvangstbevestiging` in, kies het gewenste tijdstip en vul een
notify-service in. De integratie verstuurt dan zelf de actionable melding.
Gebruik de service `pakket_tracker.confirm_received` alleen wanneer je vanuit
een eigen automation alle zichtbare pakketten wilt bevestigen. De knop
**Bezorging bevestigen** in de dagelijkse melding bevestigt sinds v0.6.2
alleen zendingen met status `delivered`; pakketten onderweg blijven openstaan.

## Dashboard openen na een melding

Gebruik op mobiele notificaties een platform-specifieke URL in `data.url`, bijvoorbeeld `/lovelace/pakketten`. Controleer de slug van jouw dashboard; URLs zijn niet op elk notify-platform hetzelfde.

## Melding bij langdurig ongewijzigd pakket

```yaml
alias: Pakket staat te lang stil
triggers:
  - trigger: numeric_state
    entity_id: sensor.pakket_tracker_lang_ongewijzigd
    above: 0
actions:
  - action: notify.mobile_app_telefoon
    data:
      title: "📦 Pakketcontrole"
      message: "Er staat al langer dan 48 uur een pakket zonder nieuwe status."
mode: single
```

De integratie levert ook `pakket_tracker_afhaalpunten` en per vervoerder
sensoren zoals `bezorgd deze maand` en `bezorgd dit jaar`.

## Melding wanneer een pakket bezorgd is

```yaml
alias: Bezorgd pakket melden
triggers:
  - trigger: event
    event_type: pakket_tracker_parcel_delivered
actions:
  - action: notify.mobile_app_telefoon
    data:
      title: "📦 Pakket bezorgd"
      message: "{{ trigger.event.data.carrier or 'Een vervoerder' }} heeft een pakket bezorgd."
      data:
        url: "/lovelace/pakketten"
mode: queued
```

Vervang `/lovelace/pakketten` door de URL van jouw dashboard. Wil je ook
nieuwe bezorgtijden melden, gebruik dan
`pakket_tracker_parcel_delivery_time_changed`; de payload bevat
`old_planned_from`, `new_planned_from`, `old_planned_to` en `new_planned_to`.
Zet geen trackingcode of adres in een lockscreen-melding.

## Maandoverzicht

De integratie levert per vervoerder én voor alle vervoerders sensoren zoals
`Bezorgd deze maand` en `Bezorgd dit jaar`. Gebruik die sensoren rechtstreeks
in een dashboard. De sensor `Bezorgd deze maand` begint op de eerste dag van
een nieuwe maand opnieuw bij nul; lees hem dan niet als het totaal van de
vorige maand. Gebruik voor een historisch maandoverzicht Recorder-statistieken
of een eigen, bewaard maandsnapshot.

## Veiligheidsregels

- Gebruik `mode: queued` voor pakketgebeurtenissen die kort na elkaar kunnen
  komen; een melding per overgang blijft dan behouden.
- Voeg een voorwaarde toe zodat een melding niet bij iedere scan opnieuw wordt verstuurd.
- Zet geen trackingcode of afleveradres in een lockscreen-notificatie.
- Entity-id's kunnen per installatie verschillen; controleer ze in **Instellingen → Apparaten & diensten → Entiteiten**.
