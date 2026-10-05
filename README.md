# Pakket Tracker NL

Een custom integration voor Home Assistant die pakketmails via IMAP herkent en
samenbrengt in één pakketoverzicht. De integratie is gericht op Nederlandse
vervoerders, maar eigen vervoerders en mailpatronen kunnen via de interface
worden toegevoegd.

Vereist Home Assistant 2025.1 of nieuwer.

**Actuele release: [0.8.2](https://github.com/Dennisd80/ha-pakket-tracker/releases/tag/v0.8.2).** PostNL-mails met `Nieuw pakket` worden nu herkend. Voor een pushbericht bij aanmelding is de [automatisering voor nieuwe pakketgebeurtenissen](https://github.com/Dennisd80/ha-pakket-tracker/wiki/Automations) nodig. Versie 0.8.1 voegde zeven Nederlandse vervoerderpresets toe; zie de [vervoerderspagina](https://github.com/Dennisd80/ha-pakket-tracker/wiki/Carriers) voor de dekking en beperkingen.
In 0.7.0 kwamen pakketgebeurtenissen, een korte statustijdlijn, een
mailboxstatussensor, herkenning van trackinglinks in HTML-mail en een
Lovelace-voorbeeld erbij. Versie 0.7.1 herstelt de statuswaarde van de nieuwe
mailboxsensor. Zie de [releasehandleiding in de wiki](https://github.com/Dennisd80/ha-pakket-tracker/wiki/Release-0.7.1)
voor voorbeelden en bekende beperkingen.

## Mogelijkheden

- Ingebouwde regels voor PostNL, DHL Parcel NL, DPD NL, GLS NL, Amazon.nl,
  bol.com, AliExpress, USPS, UPS, FedEx, Trunkrs en Budbee.
- Exacte controle van het afzenderadres om valse positieven te beperken.
- Instelbare statusteksten voor onderweg, bezorgd en gemiste bezorging.
- Vervoerder-specifieke trackingcodepatronen voor betrouwbare deduplicatie.
- Zelf een vervoerder toevoegen via naam, afzenderadres en mailteksten.
- IMAP UID-cache: alleen nieuwe mails worden opnieuw opgehaald.
- Efficiënte mailboxscan: IMAP-ophalingen in batches, vooraf gecompileerde
  regels en filtering op relevante afzenders.
- Canoniek pakketoverzicht met deduplicatie op trackingcode.
- Optionele samenvoeging met `Parcel Aggregator`-sensoren van losse
  vervoerderintegraties.
- Dagelijkse actionable notification waarmee alleen reeds bezorgde pakketten
  kunnen worden bevestigd; zendingen onderweg blijven zichtbaar.
- Herstelde sensorwaarden tijdens Home Assistant-start en niet-blokkerende
  mailboxscan.
- Optionele snellere scan na een passend `imap_content`-event van Home Assistants
  ingebouwde IMAP-integratie; de periodieke scan blijft actief.
- Korte statusgeschiedenis per zichtbaar pakket en een aparte mailboxstatussensor.
- Een voorbeeldweergave voor Lovelace in `examples/pakketoverzicht.yaml`.

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

Na een succesvolle scan publiceert de integratie pakketgebeurtenissen:
`pakket_tracker_parcel_registered`, `pakket_tracker_parcel_status_changed`,
`pakket_tracker_parcel_delivered` en
`pakket_tracker_parcel_delivery_time_changed`. De gebeurtenis bevat de
pakketvelden en `entry_id`; status- en tijdwijzigingen bevatten ook de oude en
nieuwe waarden. De eerste scan legt alleen een uitgangspunt vast en meldt
bestaande pakketten niet opnieuw. Herhaalde scans en een herstart geven geen
dubbele gebeurtenis zolang de lokale opslag beschikbaar is.
Voor pakketten zonder eigen brongeschiedenis bewaart Pakket Tracker maximaal
tien recente statusovergangen in `history`. Bestaande pakketten beginnen met
een lege geschiedenis; oude mails worden hiervoor niet als gebeurtenissen
nagespeeld. Een directe vervoerderbron kan zijn eigen geschiedenis aanleveren.

Voorbeeld: stuur één melding wanneer een pakket is bezorgd. Vervang de
notify-actie door de service van je eigen telefoon; laat de trackingcode uit
de melding om gegevens op het vergrendelscherm te beperken.

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

De nieuwe sensor **Pakket Tracker Mailbox status** toont `wachten`, `goed` of
`fout`, plus de laatste geslaagde scan en scantijden. Kies voor de voorbeeldkaart
in [examples/pakketoverzicht.yaml](examples/pakketoverzicht.yaml) de echte
entity-ID's uit jouw installatie. Het voorbeeld wordt niet automatisch aan
een bestaand dashboard toegevoegd.

### Snellere updates met IMAP Push

Als je dezelfde server, gebruikersnaam en map ook via Home Assistants ingebouwde
IMAP-integratie koppelt, reageert Pakket Tracker op nieuwe `imap_content`-events
van bekende afzenders. De ingebouwde IMAP-integratie gebruikt IMAP Push waar
de server dat ondersteunt. Pakket Tracker gebruikt het event alleen als signaal
om de eigen mailboxscan te starten; er wordt geen mailinhoud uit het event
opgeslagen. Zonder tweede IMAP-configuratie blijft het huidige scaninterval
werken. Stel in de ingebouwde IMAP-integratie bij voorkeur een aparte pakketmap
in, zodat andere mail niet op de eventbus verschijnt.
Een nieuwe mail van een bekende afzender start hoogstens één extra scan per
20 seconden; de volgende periodieke scan verwerkt de rest. Installeer de
ingebouwde IMAP-integratie alleen als je deze snellere reactie wilt.

### Bekende beperkingen in 0.7.1

- De tijdlijn begint pas bij nieuwe statusovergangen na de upgrade; oude
  mail wordt niet als gebeurtenis afgespeeld.
- Een onbekende afzender, afwijkende trackingcode of ingekorte redirectlink
  kan nog steeds een pakket missen. Meld dit met een geanonimiseerd voorbeeld.
- Zonder betrouwbare gedeelde barcode blijven e-mail- en directe bronnen
  bewust apart; zie de uitleg hieronder.
- Voor de snellere scan moeten server, gebruikersnaam en map van beide
  IMAP-integraties overeenkomen. Bij problemen blijft de periodieke scan
  werken. De [probleemoplossing in de wiki](https://github.com/Dennisd80/ha-pakket-tracker/wiki/Troubleshooting)
  geeft controles per symptoom.

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

## Credits en inspiratie

Pakket Tracker NL is een zelfstandig project. De volgende open-sourceprojecten
hebben ideeën geleverd voor de architectuur en de 0.7-release; hun code is
niet letterlijk overgenomen:

- [Home Assistant parcel integrations](https://github.com/ha-parcel-integrations)
  en [Parcel Aggregator](https://github.com/ha-parcel-integrations/ha-parcel-aggregator):
  gedeelde pakketstatussen, gebeurteniscontract en optionele samenvoeging met
  directe vervoerderbronnen.
- [Mail and Packages](https://github.com/brandon-claps/home-assistant-mail-and-packages):
  ideeën voor mailherkenning en pakketmeldingen.
- [Amazon Package Tracker](https://github.com/Huskynarr/hacs-amazon-tracker):
  snelle updates na nieuwe IMAP-mail. Wij gebruiken daarvoor optioneel
  Home Assistants ingebouwde IMAP-integratie als signaal.
- [PaketHub](https://github.com/eifeldj/pakethub):
  zichtbare diagnose, een pakketgeschiedenis en een compact pakketoverzicht.

Dank aan de makers en bijdragers van deze projecten. Pakket Tracker NL is niet
aan hen of aan de vervoerders verbonden.

## Licentie

MIT — zie [LICENSE](LICENSE).
