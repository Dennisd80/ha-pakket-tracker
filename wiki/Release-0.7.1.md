# Nieuw in Pakket Tracker NL 0.7.1

[Versie 0.7.1 op GitHub](https://github.com/Dennisd80/ha-pakket-tracker/releases/tag/v0.7.1)
bevat de uitbreidingen van 0.7.0 en een herstel voor de mailboxstatussensor.
Werk de integratie bij via HACS en herstart Home Assistant Core om nieuwe
Python-code te laden. Bestaande configuraties en vervoerderregels blijven
behouden.

## Wat is verbeterd?

| Onderdeel | Effect |
| --- | --- |
| Pakketgebeurtenissen | Automatiseringen kunnen op een nieuw pakket, statuswijziging, bezorging of verschoven bezorgvenster reageren. |
| Korte tijdlijn | Voor pakketten zonder eigen brongeschiedenis bevat `history` in de centrale `parcels`-lijst maximaal tien recente statusovergangen; directe bronnen kunnen hun eigen tijdlijn aanleveren. |
| Mailboxstatus | De nieuwe sensor **Pakket Tracker Mailbox status** toont `wachten`, `goed` of `fout`, met de laatste geslaagde scan en scantijden als attributen. |
| HTML-links | Trackingcodes in links van HTML-mails worden ook gelezen als de mail een tekstdeel heeft. De integratie haalt die links niet op. |
| Snellere reactie | Een passend `imap_content`-event van Home Assistants ingebouwde IMAP-integratie kan een extra scan starten. De periodieke scan blijft actief. |
| Dashboardvoorbeeld | [De Lovelace-voorbeeldweergave](https://github.com/Dennisd80/ha-pakket-tracker/blob/main/examples/pakketoverzicht.yaml) toont de centrale pakketlijst, mailboxstatus en recente tijdlijn. |

## Gebeurtenissen gebruiken

De integratie publiceert na een geslaagde scan:

- `pakket_tracker_parcel_registered`: een nieuw pakket verschijnt;
- `pakket_tracker_parcel_status_changed`: de status verandert, behalve de overgang naar `delivered`;
- `pakket_tracker_parcel_delivered`: een pakket krijgt status `delivered`;
- `pakket_tracker_parcel_delivery_time_changed`: het geplande venster verandert.

De payload bevat pakketvelden en `entry_id`. Statuswijzigingen hebben
`old_status` en `new_status`; vensterwijzigingen hebben `old_planned_from`,
`new_planned_from`, `old_planned_to` en `new_planned_to`. De eerste scan na
een upgrade maakt alleen een uitgangspunt: bestaande pakketten worden niet
als nieuw gemeld. Bij normale scans en herstarts voorkomt lokale opslag
dezelfde gebeurtenis opnieuw.

Voorbeeld voor een bezorgmelding zonder trackingcode op het vergrendelscherm:

```yaml
alias: Pakket bezorgd melden
triggers:
  - trigger: event
    event_type: pakket_tracker_parcel_delivered
actions:
  - action: notify.mobile_app_mijn_telefoon
    data:
      title: "📦 Pakket bezorgd"
      message: "{{ trigger.event.data.carrier or 'Een vervoerder' }} heeft een pakket bezorgd."
mode: queued
```

Vervang `notify.mobile_app_mijn_telefoon` door jouw notify-actie. Bij meerdere
IMAP-accounts kun je in een voorwaarde op `trigger.event.data.entry_id`
filteren. Zie ook [meer voorbeelden](Automations.md).

## Optionele IMAP Push

Pakket Tracker blijft zelfstandig periodiek scannen. Voor een snellere reactie:

1. Voeg via **Instellingen → Apparaten & diensten** ook Home Assistants
   [ingebouwde IMAP-integratie](https://www.home-assistant.io/integrations/imap/)
   toe.
2. Kies precies dezelfde server, gebruikersnaam en map als in Pakket Tracker.
   Gebruik bij voorkeur een aparte map met pakketmail.
3. Laat IMAP Push aan staan waar je mailserver dit ondersteunt. Een nieuwe
   mail van een ingestelde vervoerder kan dan een extra Pakket Tracker-scan
   starten.

Pakket Tracker controleert `initial`, server, gebruikersnaam, map en afzender
voordat het een event gebruikt. De extra scans zijn begrensd tot maximaal één
per 20 seconden. De mailinhoud uit het event wordt niet door Pakket Tracker
opgeslagen. Zonder ingebouwde IMAP-integratie blijft alles werken via het
ingestelde scaninterval.

## Dashboard

Gebruik [het voorbeeldbestand](https://github.com/Dennisd80/ha-pakket-tracker/blob/main/examples/pakketoverzicht.yaml)
als nieuwe Lovelace-weergave of neem de twee kaarten over. Vervang de twee
`sensor.VERVANG_...`-waarden door de echte entiteiten onder **Instellingen →
Apparaten & diensten → Entiteiten**. De `parcels`-lijst staat uitsluitend op
de centrale sensor **Pakket Tracker Totaal open**. Het voorbeeld is niet
automatisch aan een bestaand dashboard toegevoegd.

## Bekende beperkingen en controle

- De tijdlijn begint bij de eerste scan met 0.7; eerdere statusmails worden
  niet achteraf als tijdlijngebeurtenissen afgespeeld. Pakketten die verdwijnen,
  houden geen onbeperkte geschiedenis vast.
- Een onherkenbare afzender of trackingcode verschijnt niet vanzelf. Lever bij
  een foutmelding alleen een geanonimiseerd voorbeeld aan; zie [vervoerders](Carriers.md).
- Twee bronnen zonder betrouwbare gezamenlijke barcode worden niet veilig
  samengevoegd. Dezelfde zending kan dan dubbel zichtbaar zijn.
- Als IMAP Push niet werkt, controleer server, gebruikersnaam, map, afzender
  en of de ingebouwde IMAP-integratie een `imap_content`-event verstuurt.
  De volgende periodieke scan blijft het herstelpad.
- Toont de mailboxstatus `unknown`, controleer dan dat 0.7.1 geïnstalleerd is
  en dat Core na de update opnieuw is gestart. Bij `fout` helpen de
  sensorattributen en de [probleemoplossing](Troubleshooting.md).
- De voorbeeldkaart en gebeurtenissen kunnen trackinglinks en pakketdetails
  bevatten. Zet die gegevens niet zonder controle op een publiek dashboard
  of in een lockscreen-notificatie.

## Credits

Zie [Credits en inspiratie](Credits.md) voor de open-sourceprojecten waarvan
we ontwerpideeën hebben meegenomen. Pakket Tracker NL is een zelfstandig
project; er is voor deze release geen code uit die projecten gekopieerd.
