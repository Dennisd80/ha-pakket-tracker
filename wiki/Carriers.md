# Vervoerders en aangepaste regels

Sinds 0.8.2 herkent PostNL ook mails met `Nieuw pakket …` als een aangemelde
zending en `Onderweg met je pakket` als onderweg. De afzender en barcode
moeten nog steeds bij de PostNL-regel passen. Voor een pushbericht bij de
eerste herkenning is de automatisering op
`pakket_tracker_parcel_registered` uit [Voorbeeldautomatiseringen](Automations)
nodig; de integratie verstuurt niet voor iedere nieuwe mail zelf een push.

De presets bevatten onder andere PostNL, DHL Parcel NL, DPD, Amazon, bol.com, AliExpress, USPS, UPS, FedEx, Trunkrs en Budbee. Sinds 0.8.1 zijn ook Dragonfly Shipping NL, Ampère, Vinted Go, Dynalogic, Mondial Relay, InPost en Cycloon opgenomen.

## Nieuwe Nederlandse vervoerders in 0.8.1

Dragonfly is gebaseerd op berichten uit een echte mailbox: afzender `notifications@nl.dragonflyinternational.com`, de onderwerpen voor ontvangen, bezorging vandaag en bezorgd, en een gedeelde `AM…`-trackingcode uit de link. Daardoor worden opeenvolgende statusmails voor dezelfde code samengevoegd. Mondial Relay is eveneens met echte mail bevestigd: `noreply@mondialrelay.fr`, onderwerp `Behandeling van uw pakket`.

De overige nieuwe presets zijn voorlopig. Ze gebruiken een beperkt vervoerdersdomein en specifieke statuszinnen, maar er was nog geen echte notificatiemail om afzender en formuleringen volledig te controleren. Controleer na ontvangst van een eerste mail het afzenderadres en pas de regel zo nodig aan via de opties van de integratie. Cycloon herkent daarnaast FKS-trackingcodes; buiten de eigen fietssteden kan DHL de feitelijke bezorger zijn. Zonder gelijke trackingcode kan de tracker zulke berichten als aparte zendingen tonen.

Vinted Go en Mondial Relay/InPost kunnen verschillende delen van dezelfde verzending afhandelen. Ook daar is automatische samenvoeging alleen betrouwbaar als dezelfde trackingcode in beide mails staat. De nieuwe presets bezoeken geen trackingwebsites en halen geen actuele status via een vervoerdersaccount op.

## Amazon en DHL

Sinds 0.8.3 herkent de Amazon-preset ook de Engelstalige onderwerpen
`Dispatched:`, `Out for delivery:` en `Delivered:`. `Ordered:` blijft buiten
de pakketstatus: een bestelling is nog geen verzending. Zonder trackingcode
gebruikt de tracker de mailthread of het bericht als pakketidentiteit. Amazon
kan meerdere verzendingen onder één bestelnummer plaatsen; daarom wordt een
bestelnummer niet als trackingcode gebruikt. Statusmails in verschillende
threads kunnen dan als aparte pakketten verschijnen.

Amazon verstuurt soms zowel een eigen statusmail als een mail van de
daadwerkelijke bezorger. Bij een exact gelijke DHL-trackingcode (onder andere
`JJD…` en `JVGL…`) behandelt Pakket Tracker dit als één zending. De DHL-status
en -trackinglink krijgen voorrang; `Amazon.nl` blijft als herkomst zichtbaar.
Zonder gedeelde barcode worden zendingen bewust niet samengevoegd.

## Aangepaste vervoerder

Gebruik de options flow om een vervoerder toe te voegen. Vul minimaal in:

- een herkenbare naam;
- de exacte afzender of een domeinregel zoals `@voorbeeld.nl`;
- unieke onderwerpteksten voor geregistreerd, onderweg, bezorging en afgeleverd;
- alleen een trackingregex als de code betrouwbaar herkenbaar is.

Voor numerieke codes: vereis altijd een label in de regex, bijvoorbeeld:

```regex
(?:tracking|barcode|zending)[^0-9]{0,24}(\\d{9})
```

Test een nieuwe regel eerst met een echte, geanonimiseerde mail. Een te brede regel kan ordernummers of datums als pakket herkennen.

Vanaf 0.7 leest de parser ook trackinglinks in HTML-mail, zelfs als er
daarnaast een tekstdeel is. De afzenderregel en trackingregex blijven
belangrijk: een URL alleen bewijst nog niet dat een mail van de vervoerder
komt. Pakket Tracker bezoekt de links niet.
