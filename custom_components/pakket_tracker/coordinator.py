"""Coordinator voor Pakket Tracker NL.

De mailboxscan draait buiten de event-loop, gebruikt stabiele IMAP-UID's en
bewaart alleen reeds geparseerde mailvelden in Home Assistant storage. Daardoor
worden bestaande mails niet bij iedere scan opnieuw gedownload.
"""

from __future__ import annotations

import datetime
import email
import hashlib
import html as html_lib
import imaplib
import logging
import re
from datetime import timedelta
from email.header import decode_header
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CACHE_STORAGE_KEY,
    CACHE_STORAGE_VERSION,
    CARRIER_DELIVERED_SUBJECTS,
    CARRIER_DELIVERING_SUBJECTS,
    CARRIER_MISSED_SUBJECTS,
    CARRIER_NAME,
    CARRIER_REGISTERED_SUBJECTS,
    CARRIER_SENDERS,
    CARRIER_TRACKING_PATTERNS,
    CARRIER_TRANSIT_SUBJECTS,
    CONF_CARRIERS,
    CONF_FOLDER,
    CONF_IMAP_PORT,
    CONF_IMAP_SERVER,
    CONF_IMAP_SSL,
    CONF_IMAP_TIMEOUT,
    CONF_NOTIFY_SERVICE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SCAN_WINDOW_DAYS,
    CONF_USERNAME,
    DEFAULT_FOLDER,
    DEFAULT_IMAP_TIMEOUT,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_WINDOW_DAYS,
    SUMMARY_KEY,
)

_LOGGER = logging.getLogger(__name__)

_MAX_BODY_CHARS = 100_000
_UIDVALIDITY_RE = re.compile(rb"UIDVALIDITY\s+(\d+)", re.IGNORECASE)

# Veelgebruikte Nederlandse en internationale trackingformaten plus generieke
# labels. Alleen voldoende lange waarden worden geaccepteerd om orderwoorden en
# datums niet per ongeluk als trackingcode te zien.
_TRACKING_PATTERNS = (
    re.compile(r"\b(3S[A-Z0-9]{10,20})\b", re.IGNORECASE),
    re.compile(r"\b(JVGL[A-Z0-9]{8,30})\b", re.IGNORECASE),
    re.compile(
        r"(?:tracking(?:nummer|number|code)?|track\s*&\s*trace|barcode|"
        r"parcel(?:code|number)?|zending(?:nummer|code)?|shipment(?:id|number)?)"
        r"\s*(?:is|:|#|=|%3d)?\s*([A-Z0-9][A-Z0-9-]{7,31})\b",
        re.IGNORECASE,
    ),
)


class _ImapAuthenticationError(Exception):
    """IMAP heeft de accountgegevens geweigerd."""


class _ImapCommandError(Exception):
    """Een IMAP-opdracht is mislukt."""


def _decode(value: str | None) -> str:
    """Decodeer een mogelijk MIME-gecodeerde mailheader."""
    if not value:
        return ""
    decoded: list[str] = []
    for text, encoding in decode_header(value):
        if isinstance(text, bytes):
            try:
                decoded.append(text.decode(encoding or "utf-8", errors="replace"))
            except (LookupError, UnicodeError):
                decoded.append(text.decode("utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded)


def _strip_html(value: str) -> str:
    """Maak HTML geschikt voor lokale substringmatching."""
    text = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        " ",
        value,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _get_body_text(message: email.message.Message) -> str:
    """Lees text/plain, of gebruik HTML als er geen platte tekst is."""
    plain: str | None = None
    html: str | None = None
    parts = message.walk() if message.is_multipart() else [message]

    for part in parts:
        content_type = part.get_content_type()
        if content_type not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except LookupError:
                text = payload.decode("utf-8", errors="replace")
        except (TypeError, ValueError):
            continue

        if content_type == "text/plain" and plain is None:
            plain = text
        elif content_type == "text/html" and html is None:
            html = text

    body = plain if plain is not None else _strip_html(html or "")
    return body[:_MAX_BODY_CHARS]


def _message_timestamp(message: email.message.Message) -> float:
    """Zet de Date-header om naar een sorteersleutel."""
    try:
        parsed = parsedate_to_datetime(message.get("Date", ""))
        if parsed is None:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.UTC)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _parse_message(uid: str, raw_message: bytes) -> dict[str, Any]:
    """Parseer alleen velden die de pakketregels nodig hebben."""
    message = email.message_from_bytes(raw_message)
    sender_header = _decode(message.get("From", ""))
    addresses = sorted(
        {
            address.casefold()
            for _name, address in getaddresses([sender_header])
            if address
        }
    )
    return {
        "uid": uid,
        "senders": addresses,
        "subject": _decode(message.get("Subject", "")).casefold(),
        "body": _get_body_text(message).casefold(),
        "message_id": _decode(message.get("Message-ID", "")).strip().casefold(),
        "timestamp": _message_timestamp(message),
    }


def _get_uidvalidity(connection: imaplib.IMAP4, folder: str) -> str:
    """Lees UIDVALIDITY; een wijziging maakt de bestaande UID-cache ongeldig."""
    status, response = connection.status(folder, "(UIDVALIDITY)")
    if status != "OK" or not response:
        return "unknown"
    for line in response:
        if isinstance(line, bytes) and (match := _UIDVALIDITY_RE.search(line)):
            return match.group(1).decode("ascii")
    return "unknown"


def _fetch_recent_emails(
    data: dict[str, Any], cache: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    """Haal alleen nog niet gecachte IMAP-UID's op."""
    server = data[CONF_IMAP_SERVER]
    port = data[CONF_IMAP_PORT]
    use_ssl = data[CONF_IMAP_SSL]
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]
    folder = data.get(CONF_FOLDER, DEFAULT_FOLDER)
    timeout = data.get(CONF_IMAP_TIMEOUT, DEFAULT_IMAP_TIMEOUT)
    window_days = data.get(CONF_SCAN_WINDOW_DAYS, DEFAULT_SCAN_WINDOW_DAYS)

    connection = (
        imaplib.IMAP4_SSL(server, port, timeout=timeout)
        if use_ssl
        else imaplib.IMAP4(server, port, timeout=timeout)
    )
    try:
        try:
            connection.login(username, password)
        except imaplib.IMAP4.error as err:
            raise _ImapAuthenticationError from err

        status, _ = connection.select(folder, readonly=True)
        if status != "OK":
            raise _ImapCommandError(f"Mailbox {folder!r} kan niet worden geopend")

        uidvalidity = _get_uidvalidity(connection, folder)
        cached_messages = cache.get("messages", {})
        if cache.get("uidvalidity") != uidvalidity or not isinstance(
            cached_messages, dict
        ):
            cached_messages = {}

        since_date = (
            datetime.date.today() - datetime.timedelta(days=window_days)
        ).strftime("%d-%b-%Y")
        status, ids = connection.uid("search", None, f'(SINCE "{since_date}")')
        if status != "OK":
            raise _ImapCommandError(f"IMAP UID SEARCH mislukt (status={status})")

        uid_bytes = ids[0].split() if ids and ids[0] else []
        uids = [uid.decode("ascii") for uid in uid_bytes]
        current_messages: dict[str, dict[str, Any]] = {}
        fetched = 0

        for uid in uids:
            if isinstance(cached_messages.get(uid), dict):
                current_messages[uid] = cached_messages[uid]
                continue

            status, response = connection.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK" or not response:
                _LOGGER.debug("IMAP UID %s kon niet worden opgehaald", uid)
                continue

            raw_message = next(
                (
                    item[1]
                    for item in response
                    if isinstance(item, tuple)
                    and len(item) > 1
                    and isinstance(item[1], bytes)
                ),
                None,
            )
            if raw_message is None:
                continue
            current_messages[uid] = _parse_message(uid, raw_message)
            fetched += 1

        new_cache = {
            "uidvalidity": uidvalidity,
            "messages": current_messages,
            "confirmed": cache.get("confirmed", {}),
        }
        messages = [current_messages[uid] for uid in uids if uid in current_messages]
        return messages, new_cache, fetched
    finally:
        try:
            connection.logout()
        except (imaplib.IMAP4.error, OSError):
            pass


def _sender_matches(configured: list[str], actual: list[str]) -> bool:
    """Vergelijk echte addr-specs exact; '@domein' staat domeinmatching toe."""
    for rule in configured:
        normalized = rule.strip().casefold()
        if not normalized:
            continue
        if normalized.startswith("@"):
            if any(address.endswith(normalized) for address in actual):
                return True
        elif normalized in actual:
            return True
    return False


def _extract_tracking_code(
    text: str, carrier_patterns: list[str] | None = None
) -> str | None:
    """Zoek een geloofwaardige trackingcode in onderwerp en body."""
    for raw_pattern in carrier_patterns or []:
        try:
            match = re.search(raw_pattern, text, re.IGNORECASE)
        except re.error:
            _LOGGER.warning("Ongeldige trackingregex overgeslagen: %s", raw_pattern)
            continue
        if match:
            value = match.group(1) if match.lastindex else match.group(0)
            return re.sub(r"[\s-]", "", value).upper()

    for pattern in _TRACKING_PATTERNS:
        if match := pattern.search(text):
            return match.group(1).upper().replace("-", "")
    return None


def _classify_messages(
    messages: list[dict[str, Any]],
    carriers: dict[str, dict[str, Any]],
    confirmed_ids: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Classificeer mails en dedupliceer waar een pakketcode beschikbaar is."""
    result: dict[str, dict[str, Any]] = {}
    confirmed_ids = confirmed_ids or set()

    for carrier_id, rule in carriers.items():
        senders = [str(value).casefold() for value in rule.get(CARRIER_SENDERS, [])]
        patterns = {
            "registered": [
                str(value).casefold()
                for value in rule.get(CARRIER_REGISTERED_SUBJECTS, [])
            ],
            "transit": [
                str(value).casefold()
                for value in rule.get(CARRIER_TRANSIT_SUBJECTS, [])
            ],
            "delivering": [
                str(value).casefold()
                for value in rule.get(CARRIER_DELIVERING_SUBJECTS, [])
            ],
            "delivered": [
                str(value).casefold()
                for value in rule.get(CARRIER_DELIVERED_SUBJECTS, [])
            ],
            "missed": [
                str(value).casefold() for value in rule.get(CARRIER_MISSED_SUBJECTS, [])
            ],
        }
        packages: dict[str, dict[str, Any]] = {}

        for message in messages:
            if not _sender_matches(senders, message.get("senders", [])):
                continue
            haystack = f"{message.get('subject', '')} {message.get('body', '')}"

            # Een status is exclusief. De zwaarste/eindstatus wint als één mail
            # door generieke teksten meer dan één patroon bevat.
            status: str | None = None
            for candidate in (
                "missed",
                "delivered",
                "delivering",
                "transit",
                "registered",
            ):
                if any(pattern in haystack for pattern in patterns[candidate]):
                    status = candidate
                    break
            if status is None:
                continue

            tracking_code = _extract_tracking_code(
                haystack,
                [str(value) for value in rule.get(CARRIER_TRACKING_PATTERNS, [])],
            )
            message_id = message.get("message_id")
            message_fingerprint = (
                hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:16]
                if message_id
                else None
            )
            package_key = (
                f"tracking:{tracking_code}"
                if tracking_code
                else f"message:{message_fingerprint}"
                if message_fingerprint
                else f"uid:{message.get('uid')}"
            )
            parcel_id = f"email:{carrier_id}:{package_key}"
            sort_key = (
                float(message.get("timestamp") or 0),
                int(message.get("uid") or 0),
            )
            previous = packages.get(package_key)
            if previous is None or sort_key >= previous["sort_key"]:
                packages[package_key] = {
                    "id": parcel_id,
                    "status": status,
                    "tracking_code": tracking_code,
                    "sort_key": sort_key,
                    "last_seen": (
                        datetime.datetime.fromtimestamp(
                            sort_key[0], tz=datetime.UTC
                        ).isoformat()
                        if sort_key[0]
                        else None
                    ),
                }

        visible_packages = [
            package
            for package in packages.values()
            if package["id"] not in confirmed_ids
            and (
                not package["tracking_code"]
                or f"barcode:{package['tracking_code'].upper()}" not in confirmed_ids
            )
        ]
        counts: dict[str, Any] = {
            "registered": 0,
            "transit": 0,
            "delivering": 0,
            "delivered": 0,
            "packages": len(visible_packages),
            "missed": 0,
            "tracking": {
                "registered": [],
                "transit": [],
                "delivering": [],
                "delivered": [],
                "missed": [],
            },
            "parcels": [],
        }
        for package in visible_packages:
            status = package["status"]
            counts[status] += 1
            if package["tracking_code"]:
                counts["tracking"][status].append(package["tracking_code"])
            canonical_status = {
                "registered": "registered",
                "transit": "in_transit",
                "delivering": "out_for_delivery",
                "delivered": "delivered",
                "missed": "problem",
            }[status]
            counts["parcels"].append(
                {
                    "id": package["id"],
                    "carrier": rule.get(CARRIER_NAME, carrier_id),
                    "carrier_id": carrier_id,
                    "barcode": package["tracking_code"],
                    "sender": None,
                    "receiver": None,
                    "status": canonical_status,
                    "raw_status": status,
                    "delivered": status == "delivered",
                    "delivered_at": (
                        package["last_seen"] if status == "delivered" else None
                    ),
                    "planned_from": None,
                    "planned_to": None,
                    "pickup": False,
                    "pickup_point": None,
                    "url": None,
                    "source": "email",
                    "last_seen": package["last_seen"],
                }
            )
        for values in counts["tracking"].values():
            values.sort()
        counts["parcels"].sort(
            key=lambda parcel: parcel.get("last_seen") or "", reverse=True
        )
        result[carrier_id] = counts

    return result


class PakketTrackerCoordinator(DataUpdateCoordinator):
    """Haal mail op en match deze per vervoerder."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(
            hass,
            CACHE_STORAGE_VERSION,
            f"{CACHE_STORAGE_KEY}.{entry.entry_id}",
        )
        self._cache: dict[str, Any] = {}
        self._cache_loaded = False
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name="pakket_tracker",
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        if not self._cache_loaded:
            loaded = await self._store.async_load()
            self._cache = loaded if isinstance(loaded, dict) else {}
            self._cache_loaded = True

        scan_data = {
            **self.entry.data,
            CONF_IMAP_TIMEOUT: self.entry.options.get(
                CONF_IMAP_TIMEOUT, DEFAULT_IMAP_TIMEOUT
            ),
            CONF_SCAN_WINDOW_DAYS: self.entry.options.get(
                CONF_SCAN_WINDOW_DAYS, DEFAULT_SCAN_WINDOW_DAYS
            ),
        }
        try:
            messages, new_cache, fetched = await self.hass.async_add_executor_job(
                _fetch_recent_emails, scan_data, self._cache
            )
        except _ImapAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "IMAP heeft de accountgegevens geweigerd"
            ) from err
        except (OSError, TimeoutError, _ImapCommandError, imaplib.IMAP4.error) as err:
            if self.data is not None:
                _LOGGER.warning(
                    "Tijdelijke IMAP-scanfout; laatst bekende pakketdata blijft "
                    "behouden: %s",
                    err,
                )
                return self.data
            raise UpdateFailed(f"IMAP-scan mislukt: {err}") from err
        except Exception as err:  # noqa: BLE001
            if self.data is not None:
                _LOGGER.exception(
                    "Onverwachte scanfout; laatst bekende pakketdata blijft behouden"
                )
                return self.data
            raise UpdateFailed(f"Onverwachte IMAP-scanfout: {err}") from err

        if new_cache != self._cache:
            self._cache = new_cache
            try:
                await self._store.async_save(self._cache)
            except OSError as err:
                _LOGGER.warning("Pakketmailcache kon niet worden opgeslagen: %s", err)

        if fetched:
            _LOGGER.debug(
                "Pakket Tracker haalde %d nieuwe mail(s) op; %d uit cache",
                fetched,
                max(0, len(messages) - fetched),
            )
        carriers: dict[str, dict[str, Any]] = self.entry.options.get(CONF_CARRIERS, {})
        self._purge_old_confirmations()
        confirmed_ids = set(self._cache.get("confirmed", {}))
        result = _classify_messages(messages, carriers, confirmed_ids)
        result[SUMMARY_KEY] = self._build_summary(result, confirmed_ids)
        return result

    def _purge_old_confirmations(self) -> None:
        """Bewaar tombstones lang genoeg om oude mails niet terug te tonen."""
        confirmed = self._cache.get("confirmed", {})
        if not isinstance(confirmed, dict):
            self._cache["confirmed"] = {}
            return
        retention_days = (
            self.entry.options.get(CONF_SCAN_WINDOW_DAYS, DEFAULT_SCAN_WINDOW_DAYS) + 2
        )
        cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            days=retention_days
        )
        retained: dict[str, str] = {}
        for parcel_id, confirmed_at in confirmed.items():
            try:
                timestamp = datetime.datetime.fromisoformat(confirmed_at)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=datetime.UTC)
            except (TypeError, ValueError):
                continue
            if timestamp >= cutoff:
                retained[parcel_id] = confirmed_at
        self._cache["confirmed"] = retained

    def _direct_parcels(self) -> list[dict[str, Any]]:
        """Lees de canonieke parcel-lijsten van Parcel Aggregator indien aanwezig."""
        direct: dict[str, dict[str, Any]] = {}
        registry = er.async_get(self.hass)
        sources = {
            "parcel_aggregator_incoming": ("sensor.parcel_aggregator_incoming_parcels"),
            "parcel_aggregator_delivered": (
                "sensor.parcel_aggregator_delivered_parcels"
            ),
            "parcel_aggregator_awaiting_pickup": (
                "sensor.parcel_aggregator_awaiting_pickup"
            ),
        }
        for unique_id, fallback_entity_id in sources.items():
            entity_id = (
                registry.async_get_entity_id("sensor", "parcel_aggregator", unique_id)
                or fallback_entity_id
            )
            state = self.hass.states.get(entity_id)
            parcels = state.attributes.get("parcels", []) if state else []
            if not isinstance(parcels, list):
                continue
            for raw_parcel in parcels:
                if not isinstance(raw_parcel, dict):
                    continue
                parcel = dict(raw_parcel)
                carrier = str(parcel.get("carrier") or "Onbekend")
                barcode = str(parcel.get("barcode") or "").strip().upper()
                fallback = hashlib.sha256(
                    repr(sorted(parcel.items())).encode("utf-8")
                ).hexdigest()[:16]
                parcel_id = f"direct:{carrier.casefold()}:{barcode or fallback}"
                parcel.update(
                    {
                        "id": parcel_id,
                        "carrier_id": carrier.casefold().replace(" ", "_"),
                        "barcode": barcode or None,
                        "source": "parcel_aggregator",
                    }
                )
                direct[parcel_id] = parcel
        return list(direct.values())

    def _build_summary(
        self, result: dict[str, dict[str, Any]], confirmed_ids: set[str]
    ) -> dict[str, Any]:
        """Combineer mail- en directe bronnen; een directe barcode heeft voorrang."""
        merged: dict[str, dict[str, Any]] = {}
        for carrier_id, values in result.items():
            if carrier_id == SUMMARY_KEY:
                continue
            for parcel in values.get("parcels", []):
                barcode = str(parcel.get("barcode") or "").upper()
                dedupe_key = f"barcode:{barcode}" if barcode else parcel["id"]
                merged[dedupe_key] = parcel

        for parcel in self._direct_parcels():
            barcode = str(parcel.get("barcode") or "").upper()
            if parcel["id"] in confirmed_ids or (
                barcode and f"barcode:{barcode}" in confirmed_ids
            ):
                continue
            dedupe_key = f"barcode:{barcode}" if barcode else parcel["id"]
            merged[dedupe_key] = parcel

        parcels = list(merged.values())
        active_statuses = {
            "registered",
            "in_transit",
            "out_for_delivery",
            "at_pickup_point",
            "unknown",
        }
        parcels.sort(
            key=lambda parcel: (
                parcel.get("planned_from")
                or parcel.get("delivered_at")
                or parcel.get("last_seen")
                or ""
            )
        )
        return {
            "active": sum(
                1 for parcel in parcels if parcel.get("status") in active_statuses
            ),
            "out_for_delivery": sum(
                1 for parcel in parcels if parcel.get("status") == "out_for_delivery"
            ),
            "delivered_unconfirmed": sum(
                1 for parcel in parcels if parcel.get("status") == "delivered"
            ),
            "problems": sum(
                1
                for parcel in parcels
                if parcel.get("status") in {"problem", "returning"}
            ),
            "total": len(parcels),
            "parcels": parcels,
        }

    async def async_confirm_received(self) -> int:
        """Verberg alle huidige pakketten en bewaar tombstones tegen herdetectie."""
        summary = (self.data or {}).get(SUMMARY_KEY, {})
        parcels = summary.get("parcels", [])
        if not parcels:
            return 0
        confirmed = self._cache.setdefault("confirmed", {})
        now = datetime.datetime.now(datetime.UTC).isoformat()
        for parcel in parcels:
            if parcel_id := parcel.get("id"):
                confirmed[parcel_id] = now
            if barcode := str(parcel.get("barcode") or "").strip().upper():
                confirmed[f"barcode:{barcode}"] = now
        await self._store.async_save(self._cache)
        await self.async_request_refresh()
        return len(parcels)

    async def async_send_confirmation_notification(self) -> bool:
        """Vraag aan het einde van de dag of alle zichtbare pakketten binnen zijn."""
        summary = (self.data or {}).get(SUMMARY_KEY, {})
        parcels = summary.get("parcels", [])
        if not parcels:
            return False

        notify_service = self.entry.options.get(
            CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE
        )
        if not notify_service:
            return False
        if "." not in notify_service:
            _LOGGER.warning("Ongeldige notify-service: %s", notify_service)
            return False
        domain, service = notify_service.split(".", 1)
        if not self.hass.services.has_service(domain, service):
            _LOGGER.warning("Notify-service bestaat niet: %s", notify_service)
            return False

        by_status: dict[str, int] = {}
        for parcel in parcels:
            status = str(parcel.get("status") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
        status_text = ", ".join(
            f"{status.replace('_', ' ')}: {count}"
            for status, count in sorted(by_status.items())
        )
        confirm_action = f"PAKKET_TRACKER_CONFIRM_{self.entry.entry_id}"
        keep_action = f"PAKKET_TRACKER_KEEP_{self.entry.entry_id}"
        await self.hass.services.async_call(
            domain,
            service,
            {
                "title": "📦 Zijn alle pakketten ontvangen?",
                "message": (
                    f"Er staan {len(parcels)} pakket(ten) open ({status_text}). "
                    "Zijn alle verwachte bezorgingen binnen?"
                ),
                "data": {
                    "tag": f"pakket_tracker_confirmation_{self.entry.entry_id}",
                    "actions": [
                        {"action": confirm_action, "title": "Ja, alles ontvangen"},
                        {"action": keep_action, "title": "Nee, behouden"},
                    ],
                },
            },
            blocking=False,
        )
        return True
