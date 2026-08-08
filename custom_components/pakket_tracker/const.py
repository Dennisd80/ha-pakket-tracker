"""Constanten voor Pakket Tracker NL."""

DOMAIN = "pakket_tracker"
VERSION = "0.5.1"

# Config entry data (IMAP-account)
CONF_IMAP_SERVER = "imap_server"
CONF_IMAP_PORT = "imap_port"
CONF_IMAP_SSL = "imap_ssl"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_FOLDER = "folder"

# Config entry options
CONF_CARRIERS = "carriers"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_IMAP_TIMEOUT = "imap_timeout"
CONF_SCAN_WINDOW_DAYS = "scan_window_days"
CONF_CONFIRMATION_ENABLED = "confirmation_enabled"
CONF_CONFIRMATION_TIME = "confirmation_time"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_POSTAL_CODE = "postal_code"
CONF_PRESET_VERSION = "preset_version"

# Per-vervoerder velden
CARRIER_NAME = "name"
CARRIER_SENDERS = "senders"
CARRIER_REGISTERED_SUBJECTS = "registered_subjects"
CARRIER_TRANSIT_SUBJECTS = "transit_subjects"
CARRIER_DELIVERING_SUBJECTS = "delivering_subjects"
CARRIER_DELIVERED_SUBJECTS = "delivered_subjects"
CARRIER_MISSED_SUBJECTS = "missed_subjects"
CARRIER_TRACKING_PATTERNS = "tracking_patterns"
CARRIER_TRACKING_URL = "tracking_url"

DEFAULT_PORT = 993
DEFAULT_FOLDER = "INBOX"
DEFAULT_SCAN_INTERVAL = 300  # seconden
DEFAULT_IMAP_TIMEOUT = 30  # seconden per socketbewerking
DEFAULT_SCAN_WINDOW_DAYS = 2
DEFAULT_CONFIRMATION_ENABLED = True
DEFAULT_CONFIRMATION_TIME = "22:00:00"
DEFAULT_NOTIFY_SERVICE = ""
MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 3600
MIN_IMAP_TIMEOUT = 10
MAX_IMAP_TIMEOUT = 120
MIN_SCAN_WINDOW_DAYS = 1
MAX_SCAN_WINDOW_DAYS = 14
PRESET_VERSION = 4

# Persistente cache. De sleutel is entry-specifiek; UIDVALIDITY voorkomt dat
# oude UID's na een mailbox-reset aan de verkeerde mail worden gekoppeld.
CACHE_STORAGE_VERSION = 1
CACHE_STORAGE_KEY = "pakket_tracker.email_cache"

SUMMARY_KEY = "_summary"
SERVICE_CONFIRM_RECEIVED = "confirm_received"
SERVICE_KEEP_PARCELS = "keep_parcels"
ATTR_ENTRY_ID = "entry_id"

# Vooraf ingevulde vervoerdersregels. Afzenders worden exact gematcht; de
# statusteksten mogen in onderwerp of body staan. Trackingregexen draaien pas
# nadat de afzender bij de vervoerder past en veroorzaken daardoor geen brede
# numerieke matches in gewone e-mail.
PRESET_CARRIERS: dict[str, dict] = {
    "gls_nl": {
        CARRIER_NAME: "GLS NL",
        CARRIER_SENDERS: ["noreply@gls-netherlands.com"],
        CARRIER_REGISTERED_SUBJECTS: [],
        CARRIER_TRANSIT_SUBJECTS: [],
        CARRIER_DELIVERING_SUBJECTS: ["ontvang je jouw pakket"],
        CARRIER_DELIVERED_SUBJECTS: ["is bezorgd"],
        CARRIER_MISSED_SUBJECTS: [],
        CARRIER_TRACKING_PATTERNS: [],
        CARRIER_TRACKING_URL: "https://gls-group.com/NL/nl/parcel-tracking?match={code}",
    },
    "dpd_nl": {
        CARRIER_NAME: "DPD NL",
        CARRIER_SENDERS: [
            "notificaties@dpd.nl",
            "noreply@dpd.nl",
            "noreply@dpd.com",
            "noreply@dpdgroup.nl",
        ],
        CARRIER_REGISTERED_SUBJECTS: [],
        CARRIER_TRANSIT_SUBJECTS: ["pakket onderweg", "onderweg naar jou"],
        CARRIER_DELIVERING_SUBJECTS: [
            "pakket wordt vandaag",
            "bezorging vandaag",
            "wordt vandaag bezorgd",
        ],
        CARRIER_DELIVERED_SUBJECTS: ["is bezorgd", "afgeleverd", "delivered"],
        CARRIER_MISSED_SUBJECTS: ["niet bezorgd", "delivery exception"],
        CARRIER_TRACKING_PATTERNS: [
            r"(?:pakket|zending|tracking|barcode)[^0-9]{0,24}(\d{14})\b"
        ],
        CARRIER_TRACKING_URL: "https://tracking.dpd.nl/track-and-trace/{code}",
    },
    "amazon_nl": {
        CARRIER_NAME: "Amazon.nl",
        CARRIER_SENDERS: ["verzending-volgen@amazon.nl", "update-bestelling@amazon.nl"],
        CARRIER_REGISTERED_SUBJECTS: [],
        CARRIER_TRANSIT_SUBJECTS: ["wordt morgen bezorgd"],
        CARRIER_DELIVERING_SUBJECTS: ["onderweg voor bezorging"],
        CARRIER_DELIVERED_SUBJECTS: ["is bezorgd"],
        CARRIER_MISSED_SUBJECTS: [],
        CARRIER_TRACKING_PATTERNS: [],
        CARRIER_TRACKING_URL: "https://www.amazon.nl/gp/your-account/order-details?ie=UTF8&orderID={code}",
    },
    "postnl": {
        CARRIER_NAME: "PostNL",
        CARRIER_SENDERS: [
            "notificatie@edm.postnl.nl",
            "noreply@notificatie.postnl.nl",
            "noreply@postnl.nl",
            "info@postnl.nl",
            "noreply@mypostnl.nl",
        ],
        CARRIER_REGISTERED_SUBJECTS: [],
        CARRIER_TRANSIT_SUBJECTS: ["je pakket is onderweg"],
        CARRIER_DELIVERING_SUBJECTS: [
            "bezorging staat gepland",
            "wordt bezorgd",
            "bezorging vandaag",
            "verwacht tussen",
            "bezorger onderweg",
        ],
        CARRIER_DELIVERED_SUBJECTS: [
            "afgeleverd",
            "je pakket is bezorgd",
            "is bezorgd",
            "pakket bezorgd",
        ],
        CARRIER_MISSED_SUBJECTS: ["we hebben je gemist", "niet bezorgd"],
        CARRIER_TRACKING_PATTERNS: [r"\b(3S[A-Z0-9]{10,18})\b"],
        CARRIER_TRACKING_URL: "https://tracking.postnl.nl/track-and-trace/{code}",
    },
    "dhl_parcel_nl": {
        CARRIER_NAME: "DHL Parcel NL",
        CARRIER_SENDERS: [
            "noreply@dhlecommerce.nl",
            "noreply@dhl.nl",
            "donotreply_odd@dhl.com",
            "noreply@dhl.de",
            "no-reply@dhl.de",
            "support@dhl.com",
        ],
        CARRIER_REGISTERED_SUBJECTS: [],
        CARRIER_TRANSIT_SUBJECTS: ["pakket onderweg"],
        CARRIER_DELIVERING_SUBJECTS: [
            "voor de deur",
            "bezorging vandaag",
            "komt vandaag",
            "out with courier for delivery",
            "scheduled for delivery today",
        ],
        CARRIER_DELIVERED_SUBJECTS: [
            "is bezorgd",
            "pakket is afgeleverd",
            "has been delivered",
            "wurde zugestellt",
            "sendung zugestellt",
        ],
        CARRIER_MISSED_SUBJECTS: ["niet bezorgd", "delivery exception"],
        CARRIER_TRACKING_PATTERNS: [
            r"\b(JJD\d{14,25})\b",
            r"\b(JVGL[A-Z0-9]{8,30})\b",
        ],
        CARRIER_TRACKING_URL: "https://www.dhl.com/nl-nl/home/tracking.html?tracking-id={code}",
    },
    "bolcom": {
        CARRIER_NAME: "bol.com",
        CARRIER_SENDERS: [
            "noreply@bol.com",
            "service@bol.com",
            "automail@bol.com",
        ],
        CARRIER_REGISTERED_SUBJECTS: [],
        CARRIER_TRANSIT_SUBJECTS: [
            "verzonden",
            "onderweg",
            "meegegeven met",
            "bij postnl",
            "bij dhl",
        ],
        CARRIER_DELIVERING_SUBJECTS: [
            "wordt bezorgd",
        ],
        CARRIER_DELIVERED_SUBJECTS: ["bezorgd", "afgeleverd", "delivered"],
        CARRIER_MISSED_SUBJECTS: ["niet bezorgd", "bezorging gemist"],
        CARRIER_TRACKING_PATTERNS: [
            r"\b(3S[A-Z0-9]{10,18})\b",
            r"\b(JJD\d{14,25})\b",
            r"(?:pakket|zending|tracking|barcode)[^0-9]{0,24}(\d{14})\b",
        ],
        CARRIER_TRACKING_URL: "https://www.bol.com/nl/nl/track-and-trace/{code}/",
    },
    "aliexpress": {
        CARRIER_NAME: "AliExpress",
        CARRIER_SENDERS: [
            "promotion@aliexpress.com",
            "transaction@notice.aliexpress.com",
            "chocieservice@aliexpress.com",
            "aebuyersservices@aliexpress.com",
        ],
        CARRIER_REGISTERED_SUBJECTS: [],
        CARRIER_TRANSIT_SUBJECTS: [
            "package is on the way",
            "your package is on the way",
            "sendung ist unterwegs",
            "sendung wird versandt",
        ],
        CARRIER_DELIVERING_SUBJECTS: [],
        CARRIER_DELIVERED_SUBJECTS: [
            "package delivered",
            "your package has been delivered",
            "sendung zugestellt",
        ],
        CARRIER_MISSED_SUBJECTS: ["delivery failed", "delivery exception"],
        CARRIER_TRACKING_PATTERNS: [
            r"\b([A-Z]{2}\d{9}[A-Z]{2})\b",
            r"\b(\d{13})\b",
            r"\b(\d{20})\b",
        ],
        CARRIER_TRACKING_URL: "https://global.cainiao.com/detail.htm?mailNoList={code}",
    },
    "usps": {
        CARRIER_NAME: "USPS",
        CARRIER_SENDERS: [
            "auto-reply@usps.com",
            "auto-reply@tracking.usps.com",
        ],
        CARRIER_REGISTERED_SUBJECTS: [],
        CARRIER_TRANSIT_SUBJECTS: ["expected delivery on", "expected delivery by"],
        CARRIER_DELIVERING_SUBJECTS: ["out for delivery"],
        CARRIER_DELIVERED_SUBJECTS: ["item delivered"],
        CARRIER_MISSED_SUBJECTS: ["delivery exception"],
        CARRIER_TRACKING_PATTERNS: [r"\b(9[2345]\d{15,26})\b"],
        CARRIER_TRACKING_URL: "https://tools.usps.com/go/TrackConfirmAction?tLabels={code}",
    },
    "ups": {
        CARRIER_NAME: "UPS",
        CARRIER_SENDERS: ["mcinfo@ups.com", "pkginfo@ups.com"],
        CARRIER_REGISTERED_SUBJECTS: ["ups ship notification"],
        CARRIER_TRANSIT_SUBJECTS: [],
        CARRIER_DELIVERING_SUBJECTS: [
            "scheduled for delivery today",
            "follow your delivery on a live map",
            "driver is arriving soon",
        ],
        CARRIER_DELIVERED_SUBJECTS: [
            "ups package was delivered",
            "ups packages were delivered",
            "ups parcel was delivered",
            "paket wurde zugestellt",
        ],
        CARRIER_MISSED_SUBJECTS: [
            "new scheduled delivery date",
            "delivery exception",
        ],
        CARRIER_TRACKING_PATTERNS: [r"\b(1Z[0-9A-Z]{16})\b"],
        CARRIER_TRACKING_URL: "https://www.ups.com/track?loc=nl_NL&tracknum={code}",
    },
    "fedex": {
        CARRIER_NAME: "FedEx",
        CARRIER_SENDERS: [
            "trackingupdates@fedex.com",
            "fedexcanada@fedex.com",
            "noreply@fedex.com",
        ],
        CARRIER_REGISTERED_SUBJECTS: [],
        CARRIER_TRANSIT_SUBJECTS: ["shipment is on the way"],
        CARRIER_DELIVERING_SUBJECTS: [
            "delivery scheduled for today",
            "scheduled for delivery today",
            "out for delivery",
        ],
        CARRIER_DELIVERED_SUBJECTS: [
            "package has been delivered",
            "packages have been delivered",
            "shipment was delivered",
        ],
        CARRIER_MISSED_SUBJECTS: ["fedex delivery exception"],
        CARRIER_TRACKING_PATTERNS: [
            r"(?:tracking|shipment|package|barcode)[^0-9]{0,24}(\d{12,20})\b"
        ],
        CARRIER_TRACKING_URL: "https://www.fedex.com/fedextrack/?trknbr={code}",
    },
    "trunkrs": {
        CARRIER_NAME: "Trunkrs",
        CARRIER_SENDERS: ["noreply@trunkrs.nl"],
        CARRIER_REGISTERED_SUBJECTS: [
            "bevestiging aanmelding pakket",
            "is aangemeld",
            "pakket nog niet fysiek ontvangen",
        ],
        CARRIER_TRANSIT_SUBJECTS: [
            "bevestiging in sorteercentrum",
            "aangekomen in ons sorteercentrum",
        ],
        CARRIER_DELIVERING_SUBJECTS: [
            "vandaag voor de deur",
            "bezorger is onderweg",
            "onderweg voor bezorging",
            "levering vandaag",
        ],
        CARRIER_DELIVERED_SUBJECTS: ["is bezorgd", "afgeleverd"],
        CARRIER_MISSED_SUBJECTS: [
            "niet kunnen bezorgen",
            "bezorging mislukt",
            "we hebben je gemist",
        ],
        CARRIER_TRACKING_PATTERNS: [
            r"(?:pakket|trunkrsnummer|zending|tracking|barcode|afgeleverd|"
            r"sorteercentrum|aanmelding|aangemeld|bezorgd)[^0-9]{0,24}(\d{9})\b"
        ],
        CARRIER_TRACKING_URL: "https://trunkrs.nl/track-trace/?code={code}",
    },
    "budbee": {
        CARRIER_NAME: "Budbee",
        CARRIER_SENDERS: ["no-reply@budbee.com"],
        CARRIER_REGISTERED_SUBJECTS: [],
        CARRIER_TRANSIT_SUBJECTS: [],
        CARRIER_DELIVERING_SUBJECTS: [
            "vandaag bezorgd",
            "wordt vanavond bezorgd",
            "komen langs tussen",
        ],
        CARRIER_DELIVERED_SUBJECTS: [
            "is bezorgd",
            "succesvol bezorgd",
            "afgeleverd",
        ],
        CARRIER_MISSED_SUBJECTS: [
            "niet kunnen bezorgen",
            "bezorging mislukt",
        ],
        CARRIER_TRACKING_PATTERNS: [],
    },
}
