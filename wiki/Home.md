# Pakket Tracker NL

Pakket Tracker NL leest pakketstatussen uit een IMAP-mailbox en combineert die met beschikbare pakketbronnen in Home Assistant.

## Snel naar

- [Installatie en eerste configuratie](Installation.md)
- [Problemen oplossen](Troubleshooting.md)
- [Voorbeeldautomatiseringen](Automations.md)
- [Vervoerders en aangepaste regels](Carriers.md)
- [Nieuw in 0.7.1, voorbeelden en beperkingen](Release-0.7.1.md)
- [Credits en inspiratie](Credits.md)

De actuele stabiele release is **[0.7.1](https://github.com/Dennisd80/ha-pakket-tracker/releases/tag/v0.7.1)**.

Welkom bij de wiki van Pakket Tracker NL.

Nieuw in 0.7: gebeurtenissen per pakket, een korte tijdlijn met maximaal tien
eigen statusovergangen, een mailboxstatussensor, herkenning van trackinglinks in
HTML-mails en een voorbeeld voor een pakketdashboard. Optioneel laat een
`imap_content`-event van de ingebouwde Home Assistant IMAP-integratie een
snellere scan starten. De gewone periodieke scan blijft actief.

Versie 0.7.1 herstelt de waarde van de mailboxstatussensor, die in 0.7.0 op
`unknown` kon blijven staan. De [releasehandleiding](Release-0.7.1.md) bevat
installatiestappen, voorbeelden en bekende beperkingen.
