"""Constanten voor Pakket Tracker NL."""

DOMAIN = "pakket_tracker"
VERSION = "0.3.0"

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

# Per-vervoerder velden
CARRIER_NAME = "name"
CARRIER_SENDERS = "senders"
CARRIER_DELIVERING_SUBJECTS = "delivering_subjects"
CARRIER_DELIVERED_SUBJECTS = "delivered_subjects"
CARRIER_MISSED_SUBJECTS = "missed_subjects"

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

# Persistente cache. De sleutel is entry-specifiek; UIDVALIDITY voorkomt dat
# oude UID's na een mailbox-reset aan de verkeerde mail worden gekoppeld.
CACHE_STORAGE_VERSION = 1
CACHE_STORAGE_KEY = "pakket_tracker.email_cache"

SUMMARY_KEY = "_summary"
SERVICE_CONFIRM_RECEIVED = "confirm_received"
SERVICE_KEEP_PARCELS = "keep_parcels"
ATTR_ENTRY_ID = "entry_id"

# Vooraf ingevulde vervoerdersregels. Alle vijf zijn bevestigd met echte
# voorbeeldmails (afzender + patroon in onderwerp en/of body).
PRESET_CARRIERS: dict[str, dict] = {
    "gls_nl": {
        CARRIER_NAME: "GLS NL",
        CARRIER_SENDERS: ["noreply@gls-netherlands.com"],
        CARRIER_DELIVERING_SUBJECTS: ["ontvang je jouw pakket"],
        CARRIER_DELIVERED_SUBJECTS: ["is bezorgd"],
        CARRIER_MISSED_SUBJECTS: [],
    },
    "dpd_nl": {
        CARRIER_NAME: "DPD NL",
        CARRIER_SENDERS: ["notificaties@dpd.nl"],
        CARRIER_DELIVERING_SUBJECTS: ["pakket wordt vandaag"],
        CARRIER_DELIVERED_SUBJECTS: ["is bezorgd"],
        CARRIER_MISSED_SUBJECTS: [],
    },
    "amazon_nl": {
        CARRIER_NAME: "Amazon.nl",
        CARRIER_SENDERS: ["verzending-volgen@amazon.nl", "update-bestelling@amazon.nl"],
        CARRIER_DELIVERING_SUBJECTS: ["onderweg voor bezorging"],
        CARRIER_DELIVERED_SUBJECTS: ["is bezorgd"],
        CARRIER_MISSED_SUBJECTS: [],
    },
    "postnl": {
        CARRIER_NAME: "PostNL",
        CARRIER_SENDERS: ["notificatie@edm.postnl.nl"],
        CARRIER_DELIVERING_SUBJECTS: ["bezorging staat gepland"],
        CARRIER_DELIVERED_SUBJECTS: ["afgeleverd"],
        CARRIER_MISSED_SUBJECTS: [],
    },
    "dhl_parcel_nl": {
        CARRIER_NAME: "DHL Parcel NL",
        CARRIER_SENDERS: ["noreply@dhlecommerce.nl"],
        CARRIER_DELIVERING_SUBJECTS: ["voor de deur"],
        CARRIER_DELIVERED_SUBJECTS: ["is bezorgd"],
        CARRIER_MISSED_SUBJECTS: [],
    },
}
