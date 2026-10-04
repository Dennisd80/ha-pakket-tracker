# Vervoerders en aangepaste regels

De presets bevatten onder andere PostNL, DHL Parcel NL, DPD, Amazon, bol.com, AliExpress, USPS, UPS, FedEx, Trunkrs en Budbee.

## Amazon en DHL

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
