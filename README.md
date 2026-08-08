# Pakket Tracker NL

Een custom integration voor Home Assistant die pakketmails via IMAP herkent en
samenbrengt in één pakketoverzicht. De integratie is gericht op Nederlandse
vervoerders, maar eigen vervoerders en mailpatronen kunnen via de interface
worden toegevoegd.

Vereist Home Assistant 2025.1 of nieuwer.

## Mogelijkheden

- Ingebouwde regels voor PostNL, DHL Parcel NL, DPD NL, GLS NL, Amazon.nl,
  bol.com, AliExpress, USPS, UPS, FedEx, Trunkrs en Budbee.
- Exacte controle van het afzenderadres om valse positieven te beperken.
- Instelbare statusteksten voor onderweg, bezorgd en gemiste bezorging.
- Vervoerder-specifieke trackingcodepatronen voor betrouwbare deduplicatie.
- Zelf een vervoerder toevoegen via naam, afzenderadres en mailteksten.
- IMAP UID-cache: alleen nieuwe mails worden opnieuw opgehaald.
- Canoniek pakketoverzicht met deduplicatie op trackingcode.
- Optionele samenvoeging met `Parcel Aggregator`-sensoren van losse
  vervoerderintegraties.
- Dagelijkse actionable notification met de vraag of alles ontvangen is.
- Herstelde sensorwaarden tijdens Home Assistant-start en niet-blokkerende
  mailboxscan.

Bij een upgrade worden nieuwe ingebouwde vervoerders eenmalig toegevoegd aan
bestaande configuraties. Eigen namen en regels blijven behouden. Een
vervoerder die daarna bewust wordt verwijderd, wordt niet opnieuw aangemaakt.

## Installatie via HACS

1. Open HACS in Home Assistant.
2. Ga naar **Integraties**, open het menu en kies **Aangepaste repositories**.
3. Voeg `https://github.com/Dennisd80/ha-pakket-tracker` toe als categorie
   **Integratie**.
4. Installeer **Pakket Tracker NL** en herstart Home Assistant.
5. Ga naar **Instellingen → Apparaten & diensten → Integratie toevoegen** en
   zoek naar **Pakket Tracker NL**.

Handmatig installeren kan door `custom_components/pakket_tracker` naar de map
`custom_components` van Home Assistant te kopiëren.

## IMAP instellen

Gebruik bij Gmail bij voorkeur een afzonderlijk app-wachtwoord en nooit het
normale accountwachtwoord. IMAP moet voor de mailbox beschikbaar zijn. Andere
IMAP-providers werken ook; vul dan hun server, poort en map in.

Na de eerste configuratie kunnen onder **Configureren** vervoerders,
scaninterval, time-out, terugkijkvenster en de dagelijkse bevestiging worden
aangepast. Voor actionable notifications vul je een bestaande service in,
bijvoorbeeld `notify.mobile_app_mijn_telefoon`.

## Sensoren en services

Per vervoerder worden tellers aangemaakt voor `registered`, `transit`,
`delivering`, `delivered`, `packages` en `missed`. Hierdoor wordt een vooraf
aangemeld pakket niet ten onrechte als vandaag onderweg gemeld. Daarnaast zijn
er centrale sensoren voor actieve
pakketten, vandaag onderweg, onbevestigd bezorgd, problemen en totaal open.
De attribuutlijst `parcels` staat alleen op de centrale totaalsensor.

Beschikbare services:

- `pakket_tracker.confirm_received`: markeert de huidige pakketten als
  ontvangen en voorkomt herdetectie vanuit recente mails.
- `pakket_tracker.keep_parcels`: laat de huidige pakketten openstaan.

## Combineren met losse vervoerderintegraties

Wanneer de optionele Parcel Aggregator-entiteiten bestaan, leest Pakket Tracker
NL de attributen van de inkomende, bezorgde en afhaalpuntsensoren mee. Een
directe bron met dezelfde trackingcode krijgt voorrang op een maildetectie.
Zonder Parcel Aggregator blijft de IMAP-functionaliteit zelfstandig werken.

## Privacy

Accountgegevens worden door Home Assistant lokaal in de config-entryopslag
bewaard en horen nooit in deze repository. Voor snelle herscans bewaart de
integratie lokaal een tijdelijke cache met geparseerde afzenders, onderwerpen
en berichttekst in `.storage`; die data wordt niet in diagnostiek opgenomen.
Diagnostiek maskeert gebruikersnaam, wachtwoord en notify-service.

Publiceer nooit `secrets.yaml`, bestanden uit `.storage`, Home Assistant-logs of
onbewerkte pakketmails in een issue. Zie ook [SECURITY.md](SECURITY.md).

Een custom Track & Trace-template met `{postal_code}` kan de postcode opnemen
in het `tracking_url`-attribuut dat Home Assistant Recorder opslaat. Gebruik
bij voorkeur alleen `{code}`, of sluit de betreffende summary-sensor uit in
Recorder. De postcode wordt wel uit diagnostics geredigeerd.

Pakketten zonder barcode kunnen niet veilig tussen e-mail en Parcel Aggregator
worden samengevoegd zonder risico op false merges. De integratie houdt zulke
bronnen daarom bewust apart; gebruik een betrouwbare trackingregex als je
cross-source deduplicatie nodig hebt.

## Bijdragen

Issues en pull requests zijn welkom. Nieuwe vervoerderregels moeten bij voorkeur
worden onderbouwd met geanonimiseerde voorbeelden van afzender en relevante
statusteksten. Zie [CONTRIBUTING.md](CONTRIBUTING.md).

## Licentie

MIT — zie [LICENSE](LICENSE).
