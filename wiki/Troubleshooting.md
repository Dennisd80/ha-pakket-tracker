# Problemen oplossen

## Mailboxstatus staat op `unknown` of `fout`

Controleer bij `unknown` eerst of **0.7.1 of nieuwer** is geïnstalleerd en
Home Assistant Core na de update is herstart. Versie 0.7.0 kon de waarde
van deze nieuwe sensor nog niet tonen. Bij `fout` zijn de laatste geslaagde
scan, het aantal opeenvolgende fouten en de scantijden beschikbaar als
sensorattributen. Controleer daarna de IMAP-instellingen en de diagnostiek
onder de Pakket Tracker-configuratie-entry.

## Geen snelle scan na een nieuwe mail

De snelle scan gebruikt optioneel het `imap_content`-event van Home Assistants
ingebouwde IMAP-integratie. Controleer of deze tweede integratie werkelijk
dezelfde server, gebruikersnaam en map gebruikt, of IMAP Push op jouw server
werkt en of de afzender in Pakket Tracker is ingesteld. Alleen events met
`initial: true` tellen mee. Extra scans zijn begrensd tot één per 20 seconden;
de periodieke scan blijft altijd actief.

## Geen pakketgebeurtenis of lege tijdlijn

De eerste scan na de upgrade legt alleen een uitgangspunt vast. Oude
statusmails worden niet opnieuw als gebeurtenissen gepubliceerd. De tijdlijn
groeit pas als een zichtbaar pakket later van status verandert. Kijk in
**Ontwikkelaarstools → Gebeurtenissen** naar bijvoorbeeld
`pakket_tracker_parcel_delivered`. Als de lokale cache wordt verwijderd, kan
de uitgangssituatie opnieuw beginnen.

## HTML-mail wordt nog niet herkend

Versie 0.7 leest trackinglinks uit HTML, ook als een tekstdeel aanwezig is.
Een onbekende afzender, afwijkende code of ingekorte redirectlink kan nog
steeds ontbreken. Controleer de ingestelde vervoerderregel en meld een
geanonimiseerd voorbeeld; deel geen complete mail of echte barcode publiek.

## `invalid_auth` of IMAP-scanfout

Controleer app-wachtwoord, IMAP-server, SSL/poort en de mapnaam. Bij tijdelijke netwerkproblemen blijft de laatst bekende data kort zichtbaar. Na drie opeenvolgende scanfouten markeert de coordinator de update als mislukt. Bekijk de sensorattributen `scan_error` en `consecutive_scan_failures`.

## Pakket telt dubbel

Controleer of de vervoerder een trackingcode in de mail zet. Statusmails in dezelfde thread met precies één code worden samengevoegd. Threads met meerdere codes worden bewust niet samengevoegd om verschillende pakketten niet kwijt te raken.

### Amazon en DHL worden nog afzonderlijk getoond

De automatische samenvoeging werkt alleen wanneer beide mails exact dezelfde
DHL-trackingcode bevatten. Controleer of de Amazon-mail een code begint met
`JJD` of `JVGL` bevat en of DHL diezelfde code in de eigen mail zet. Een
Amazon-bestelnummer is geen DHL-trackingcode en wordt niet gebruikt voor
deduplicatie, om verschillende zendingen niet onterecht samen te voegen.

## Een nummer wordt ten onrechte als trackingcode gezien

Gebruik bij een aangepaste numerieke regex altijd context zoals `tracking`, `barcode`, `zending` of `shipment`. Losse ordernummers, telefoonnummers en datums worden door de ingebouwde guard geweerd.

## Oude sensor blijft zichtbaar na verwijderen vervoerder

Herlaad de Pakket Tracker-integratie of herstart Home Assistant. Sinds 0.4.2 worden wees-sensoren bij het opzetten van de sensorplatform automatisch opgeruimd.

## `template_migration` importfout

Deze oude migratiehulp is alleen nodig voor legacy-templateconfiguratie. Gebruik de actuele versie van de integratie; controleer na een HA-update of interne template-constantnamen zijn gewijzigd. Verwijder de integratie als de migratie al voltooid is.

## `alert` configuratiefout

Controleer de YAML-inspringing en Jinja-blokken. Elk `{% for %}` moet exact één `{% endfor %}` hebben; een losse `{% endif %}` veroorzaakt een setup-fout.

## Diagnostiek delen

De diagnostics-uitvoer bevat geen mailboxinhoud of wachtwoord. Deel toch geen volledige e-mailheaders, adressen of trackingcodes publiek; anonimiseer ze eerst.

## Track & Trace-link ontbreekt

Controleer of de mail een herkenbare trackingcode bevat en of de vervoerder een
`tracking_url`-template heeft. Een aangepaste vervoerder kan in de options flow
een template gebruiken met `{code}` en optioneel `{postal_code}`.

## Statistieken lijken te laag

De bezorgteller telt alleen unieke pakketten wanneer ze via de ontvangstactie
worden bevestigd. Controleer daarom de bevestigingsmelding en gebruik geen
zichtbare pakketstand als cumulatieve teller.

## Barcode-loze dubbele bron

Een pakket zonder barcode kan niet veilig tussen e-mail en Parcel Aggregator
worden samengevoegd zonder risico op het samenvoegen van twee verschillende
pakketten. De integratie houdt daarom bewust beide bronnen apart. Gebruik een
carrier-regel die de trackingcode betrouwbaar extraheert als je dit wilt
voorkomen.

## Privacy bij postcode in een trackinglink

Een custom URL-template met `{postal_code}` kan de postcode in het
`tracking_url`-attribuut zetten. Home Assistant Recorder kan dat attribuut
opslaan. Gebruik daarom bij voorkeur alleen `{code}`, of sluit de betreffende
summary-sensor uit in Recorder, bijvoorbeeld:

```yaml
recorder:
  exclude:
    entities:
      - sensor.VERVANG_DOOR_JOUW_CENTRALE_TOTAALSENSOR
```

De voorbeeldnaam hierboven is een invulplek. Controleer de echte entity-ID
onder **Instellingen → Apparaten & diensten → Entiteiten**.
