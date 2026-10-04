# Installatie en configuratie

## Installatie via HACS

1. Open HACS → Integraties.
2. Open het menu **Aangepaste repositories** en voeg
   `https://github.com/Dennisd80/ha-pakket-tracker` toe als **Integratie**.
3. Zoek naar **Pakket Tracker NL** en installeer de nieuwste release (nu 0.7.1).
4. Herstart Home Assistant.
5. Voeg de integratie toe via Instellingen → Apparaten & diensten → Integratie toevoegen.

Gebruik voor Gmail een afzonderlijk app-wachtwoord. Controleer bij andere
mailproviders welke IMAP-aanmeldmethode ze ondersteunen; Microsoft 365 en
Outlook-accounts die alleen OAuth2 toelaten werken niet met deze
wachtwoordgebaseerde IMAP-koppeling. Zet nooit accountgegevens in een issue,
automation of dashboard.

## Eerste controle

- Controleer server, poort, SSL, gebruikersnaam en map (`INBOX`).
- Test de verbinding in de config flow.
- Kies alleen relevante vervoerders om onnodige scans te beperken.
- Vul optioneel een notify-service in voor de dagelijkse bevestiging.
- Vul optioneel je postcode in als een Track & Trace-provider die gebruikt.

Na installatie maakt de integratie per vervoerder Track & Trace-links en
sensoren voor bezorgd totaal, deze week, deze maand en dit jaar aan.

Sinds 0.7.1 is er ook een sensor **Pakket Tracker Mailbox status**. Die toont
`wachten`, `goed` of `fout`; de entiteit-ID hangt van jouw installatie af.
Nieuwe pakketgebeurtenissen en de korte tijdlijn staan beschreven in
[Nieuw in 0.7.1](Release-0.7.1.md).

Voor optionele snelle updates kun je daarnaast Home Assistants
[ingebouwde IMAP-integratie](https://www.home-assistant.io/integrations/imap/)
op dezelfde server, gebruikersnaam en map instellen. Dit is geen vereiste:
Pakket Tracker blijft zelfstandig periodiek scannen. Gebruik bij voorkeur
een aparte pakketmap voor deze tweede IMAP-koppeling.

Na een wijziging is een integratieherlaadactie of Core-herstart nodig voordat nieuwe code/configuratie actief is.
