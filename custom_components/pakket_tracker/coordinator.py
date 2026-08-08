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
from urllib.parse import quote

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
    CARRIER_TRACKING_URL,
    CARRIER_TRANSIT_SUBJECTS,
    CONF_CARRIERS,
    CONF_FOLDER,
    CONF_IMAP_PORT,
    CONF_IMAP_SERVER,
    CONF_IMAP_SSL,
    CONF_IMAP_TIMEOUT,
    CONF_NOTIFY_SERVICE,
    CONF_PASSWORD,
    CONF_POSTAL_CODE,
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
_MESSAGE_ID_RE = re.compile(r"<[^<>]+>")
_FETCH_UID_RE = re.compile(rb"\bUID\s+(\d+)", re.IGNORECASE)
_CACHE_PARSER_VERSION = 2
_MAX_CONSECUTIVE_SCAN_FAILURES = 3

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


def _first_message_id(value: str | None) -> str | None:
    """Geef de eerste genormaliseerde Message-ID uit een mailheader terug."""
    decoded = _decode(value).strip().casefold()
    if not decoded:
        return None
    if matches := _MESSAGE_ID_RE.findall(decoded):
        return matches[0]
    return decoded.split()[0]


def _normalize_code(value: str | None) -> str | None:
    """Normaliseer barcodes voor extractie, deduplicatie en tombstones."""
    if not value:
        return None
    return re.sub(r"[\s-]", "", str(value)).upper() or None


def _build_tracking_url(
    code: str | None, rule: dict[str, Any], postal_code: str = ""
) -> str | None:
    """Vul een configureerbare vervoerder-URL zonder gevoelige data te loggen."""
    template = str(rule.get(CARRIER_TRACKING_URL) or "").strip()
    if not code or not template:
        return None
    try:
        return template.format(
            code=quote(code, safe=""),
            postal_code=quote(postal_code.strip(), safe=""),
        )
    except (KeyError, ValueError):
        _LOGGER.warning("Ongeldige tracking-URL-template overgeslagen")
        return None


def _timestamp_after(value: object, cutoff: datetime.datetime) -> bool:
    try:
        timestamp = datetime.datetime.fromisoformat(str(value))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=datetime.UTC)
    except (TypeError, ValueError):
        return False
    return timestamp >= cutoff
def _planned_delivery_window(
    haystack: str,
    timestamp: float,
    time_zone: datetime.tzinfo,
) -> tuple[str | None, str | None]:
    """Leid een geplande bezorgdag af uit relatieve tekst in de mail."""
    if not timestamp:
        return None, None
    if "wordt morgen bezorgd" not in haystack:
        return None, None

    delivery_date = (
        datetime.datetime.fromtimestamp(timestamp, tz=time_zone).date()
        + datetime.timedelta(days=1)
    )
    planned_from = datetime.datetime.combine(
        delivery_date, datetime.time.min, tzinfo=time_zone
    )
    planned_to = datetime.datetime.combine(
        delivery_date, datetime.time.max, tzinfo=time_zone
    )
    return planned_from.isoformat(), planned_to.isoformat()


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
    message_id = _first_message_id(message.get("Message-ID"))
    thread_id = (
        _first_message_id(message.get("References"))
        or _first_message_id(message.get("In-Reply-To"))
        or message_id
    )
    return {
        "uid": uid,
        "senders": addresses,
        "subject": _decode(message.get("Subject", "")).casefold(),
        "body": _get_body_text(message).casefold(),
        "message_id": message_id,
        "thread_id": thread_id,
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
        if cache.get("parser_version") != _CACHE_PARSER_VERSION:
            # Nieuwe parservelden vereisen een eenmalige refetch. Bevestigde
            # pakketten blijven buiten deze berichtcache behouden.
            cached_messages = {}
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

        uncached = [uid for uid in uids if uid not in cached_messages]
        for uid in uids:
            if isinstance(cached_messages.get(uid), dict):
                current_messages[uid] = cached_messages[uid]

        if uncached:
            fetch_status, fetch_response = connection.uid(
                "fetch", ",".join(uncached), "(UID BODY.PEEK[])"
            )
            fetched_messages: dict[str, bytes] = {}
            if fetch_status == "OK":
                for item in fetch_response or []:
                    if not isinstance(item, tuple) or len(item) < 2:
                        continue
                    header, raw_message = item[0], item[1]
                    if not isinstance(header, bytes) or not isinstance(
                        raw_message, bytes
                    ):
                        continue
                    match = _FETCH_UID_RE.search(header)
                    if match:
                        fetched_messages[match.group(1).decode("ascii")] = raw_message
            # Some IMAP servers do not support a multi-UID FETCH. Keep a
            # compatible per-UID fallback instead of losing new messages.
            if len(fetched_messages) < len(uncached):
                for uid in uncached:
                    if uid in fetched_messages:
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
                    if isinstance(raw_message, bytes):
                        fetched_messages[uid] = raw_message
            for uid, raw_message in fetched_messages.items():
                current_messages[uid] = _parse_message(uid, raw_message)
                fetched += 1

        new_cache = {
            "parser_version": _CACHE_PARSER_VERSION,
            "uidvalidity": uidvalidity,
            "messages": current_messages,
            "confirmed": cache.get("confirmed", {}),
            "delivery_events": cache.get("delivery_events", []),
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
            # Broad numeric custom patterns need a nearby tracking label. This
            # prevents order numbers, dates and phone numbers becoming parcels.
            if (
                r"\d" in raw_pattern
                and not re.search(
                    r"tracking|barcode|zending|shipment|parcel|trunkrsnummer|awb",
                    raw_pattern,
                    re.IGNORECASE,
                )
            ):
                context = text[max(0, match.start() - 48) : match.start()]
                if not re.search(
                    r"tracking|barcode|zending|shipment|parcel|trunkrsnummer|awb",
                    context,
                    re.IGNORECASE,
                ):
                    continue
            return _normalize_code(value)

    for pattern in _TRACKING_PATTERNS:
        if match := pattern.search(text):
            return _normalize_code(match.group(1))
    return None


def _stable_direct_parcel_key(parcel: dict[str, Any], carrier: str) -> str:
    """Maak een fallback-id uit velden die niet door statusupdates wijzigen."""
    for field in ("parcel_id", "package_id", "shipment_id", "reference", "id"):
        value = parcel.get(field)
        if value not in (None, "") and not isinstance(value, dict | list):
            return str(value).strip().casefold()
    stable_fields = (
        "carrier",
        "sender",
        "receiver",
        "url",
        "tracking_url",
        "created_at",
        "first_seen",
        "date",
        "title",
    )
    payload = tuple(
        (field, str(parcel.get(field) or "").strip().casefold())
        for field in stable_fields
    )
    return hashlib.sha256(
        repr((carrier.casefold(), payload)).encode("utf-8")
    ).hexdigest()[:16]


def _classify_messages(
    messages: list[dict[str, Any]],
    carriers: dict[str, dict[str, Any]],
    confirmed_ids: set[str] | None = None,
    time_zone: datetime.tzinfo = datetime.UTC,
    postal_code: str = "",
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

        # If a thread contains exactly one tracking code, apply it to all
        # status mails in that thread. If it contains multiple codes, keep the
        # per-mail tracking keys to avoid merging unrelated parcels.
        thread_codes: dict[str, set[str]] = {}
        for candidate in messages:
            if not _sender_matches(senders, candidate.get("senders", [])):
                continue
            candidate_text = (
                f"{candidate.get('subject', '')} {candidate.get('body', '')}"
            )
            if not any(
                pattern in candidate_text
                for values in patterns.values()
                for pattern in values
            ):
                continue
            candidate_code = _extract_tracking_code(
                candidate_text,
                [str(value) for value in rule.get(CARRIER_TRACKING_PATTERNS, [])],
            )
            candidate_thread = candidate.get("thread_id")
            if candidate_code and candidate_thread:
                thread_codes.setdefault(candidate_thread, set()).add(candidate_code)

        for message in messages:
            if not _sender_matches(senders, message.get("senders", [])):
                continue
            haystack = f"{message.get('subject', '')} {message.get('body', '')}"

            # Een status is exclusief. De zwaarste/eindstatus wint als één mail
            # door generieke teksten meer dan één patroon bevat. Een expliciete
            # afspraak voor morgen blijft wel transit: zulke Amazon-mails kunnen
            # daarnaast algemene tekst over "onderweg voor bezorging" bevatten.
            status: str | None = None
            if "wordt morgen bezorgd" in haystack and any(
                pattern in haystack for pattern in patterns["transit"]
            ):
                status = "transit"
            else:
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
            thread_id = message.get("thread_id")
            thread_fingerprint = (
                hashlib.sha256(thread_id.encode("utf-8")).hexdigest()[:16]
                if thread_id
                else None
            )
            if (
                not tracking_code
                and thread_id
                and len(thread_codes.get(thread_id, set())) == 1
            ):
                tracking_code = next(iter(thread_codes[thread_id]))
            package_key = (
                f"tracking:{tracking_code}"
                if tracking_code
                else f"thread:{thread_fingerprint}"
                if thread_fingerprint
                else f"message:{message_fingerprint}"
                if message_fingerprint
                else f"uid:{message.get('uid')}"
            )
            parcel_id = f"email:{carrier_id}:{package_key}"
            sort_key = (
                float(message.get("timestamp") or 0),
                int(message.get("uid") or 0),
            )
            planned_from, planned_to = _planned_delivery_window(
                haystack, sort_key[0], time_zone
            )
            previous = packages.get(package_key)
            if previous is None or sort_key >= previous["sort_key"]:
                packages[package_key] = {
                    "id": parcel_id,
                    "status": status,
                    "tracking_code": tracking_code,
                    "tracking_url": _build_tracking_url(
                        tracking_code, rule, postal_code
                    ),
                    "sort_key": sort_key,
                    "planned_from": planned_from,
                    "planned_to": planned_to,
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
                    "planned_from": package["planned_from"],
                    "planned_to": package["planned_to"],
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


def _threading_diagnostics(
    messages: list[dict[str, Any]], carriers: dict[str, dict[str, Any]]
) -> dict[str, dict[str, int]]:
    """Tel threadingkenmerken van pakketmails zonder mailgegevens te tonen."""
    diagnostics: dict[str, dict[str, int]] = {}
    status_keys = (
        CARRIER_REGISTERED_SUBJECTS,
        CARRIER_TRANSIT_SUBJECTS,
        CARRIER_DELIVERING_SUBJECTS,
        CARRIER_DELIVERED_SUBJECTS,
        CARRIER_MISSED_SUBJECTS,
    )
    for carrier_id, rule in carriers.items():
        senders = [str(value).casefold() for value in rule.get(CARRIER_SENDERS, [])]
        patterns = [
            str(pattern).casefold()
            for key in status_keys
            for pattern in rule.get(key, [])
        ]
        custom_tracking_patterns = [
            str(value) for value in rule.get(CARRIER_TRACKING_PATTERNS, [])
        ]
        recognized = 0
        explicitly_threaded = 0
        thread_groups: dict[str, list[str | None]] = {}
        for message in messages:
            if not _sender_matches(senders, message.get("senders", [])):
                continue
            haystack = f"{message.get('subject', '')} {message.get('body', '')}"
            if not any(pattern in haystack for pattern in patterns):
                continue
            recognized += 1
            message_id = message.get("message_id")
            thread_id = message.get("thread_id")
            if thread_id and message_id and thread_id != message_id:
                explicitly_threaded += 1
            if thread_id:
                thread_groups.setdefault(thread_id, []).append(
                    _extract_tracking_code(haystack, custom_tracking_patterns)
                )

        multi_message_groups = [
            codes for codes in thread_groups.values() if len(codes) > 1
        ]
        diagnostics[carrier_id] = {
            "recognized_status_messages": recognized,
            "messages_with_thread_relation": explicitly_threaded,
            "multi_message_thread_groups": len(multi_message_groups),
            "thread_groups_with_multiple_tracking_codes": sum(
                1
                for codes in multi_message_groups
                if len({code for code in codes if code}) > 1
            ),
        }
    return diagnostics


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
        self.threading_diagnostics: dict[str, dict[str, int]] = {}
        self.consecutive_scan_failures = 0
        self.last_scan_error: str | None = None
        self.last_successful_scan: str | None = None
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
            self.consecutive_scan_failures += 1
            self.last_scan_error = str(err)
            if self.data is not None:
                _LOGGER.warning(
                    "Tijdelijke IMAP-scanfout; laatst bekende pakketdata blijft "
                    "behouden: %s",
                    err,
                )
                if self.consecutive_scan_failures >= _MAX_CONSECUTIVE_SCAN_FAILURES:
                    raise UpdateFailed(f"IMAP-scan mislukt: {err}") from err
                return self.data
            raise UpdateFailed(f"IMAP-scan mislukt: {err}") from err
        except Exception as err:  # noqa: BLE001
            self.consecutive_scan_failures += 1
            self.last_scan_error = str(err)
            if self.data is not None:
                _LOGGER.exception(
                    "Onverwachte scanfout; laatst bekende pakketdata blijft behouden"
                )
                if self.consecutive_scan_failures >= _MAX_CONSECUTIVE_SCAN_FAILURES:
                    raise UpdateFailed(f"Onverwachte IMAP-scanfout: {err}") from err
                return self.data
            raise UpdateFailed(f"Onverwachte IMAP-scanfout: {err}") from err

        if new_cache != self._cache:
            self._cache = new_cache
            try:
                await self._store.async_save(self._cache)
            except OSError as err:
                _LOGGER.warning("Pakketmailcache kon niet worden opgeslagen: %s", err)

        self.consecutive_scan_failures = 0
        self.last_scan_error = None
        self.last_successful_scan = datetime.datetime.now(datetime.UTC).isoformat()

        if fetched:
            _LOGGER.debug(
                "Pakket Tracker haalde %d nieuwe mail(s) op; %d uit cache",
                fetched,
                max(0, len(messages) - fetched),
            )
        carriers: dict[str, dict[str, Any]] = self.entry.options.get(CONF_CARRIERS, {})
        self._purge_old_confirmations()
        confirmed_ids = set(self._cache.get("confirmed", {}))
        time_zone = dt_util.get_time_zone(self.hass.config.time_zone) or datetime.UTC
        self.threading_diagnostics = _threading_diagnostics(messages, carriers)
        result = _classify_messages(
            messages,
            carriers,
            confirmed_ids,
            time_zone=time_zone,
            postal_code=self.entry.options.get(CONF_POSTAL_CODE, ""),
        )
        result[SUMMARY_KEY] = self._build_summary(result, confirmed_ids)
        result[SUMMARY_KEY]["delivery_statistics"] = self._delivery_statistics()
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
                normalized_id = parcel_id
                if parcel_id.startswith("barcode:"):
                    barcode = _normalize_code(parcel_id.removeprefix("barcode:"))
                    if barcode:
                        normalized_id = f"barcode:{barcode}"
                retained[normalized_id] = confirmed_at
        self._cache["confirmed"] = retained
        events = self._cache.get("delivery_events", [])
        if isinstance(events, list):
            event_cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
                days=370
            )
            self._cache["delivery_events"] = [
                event
                for event in events
                if isinstance(event, dict)
                and str(event.get("timestamp", ""))
                and _timestamp_after(event.get("timestamp"), event_cutoff)
            ]
    def _delivery_statistics(self) -> dict[str, dict[str, int]]:
        """Bereken totaal/week/maand/jaar uit unieke bevestigingsevents."""
        events = self._cache.get("delivery_events", [])
        if not isinstance(events, list):
            return {}
        now = datetime.datetime.now(datetime.UTC)
        start_week = now - datetime.timedelta(days=now.weekday())
        start_week = start_week.replace(hour=0, minute=0, second=0, microsecond=0)
        start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_year = now.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        stats: dict[str, dict[str, int]] = {}
        for event in events:
            if not isinstance(event, dict):
                continue
            carrier_id = str(event.get("carrier_id") or "unknown")
            try:
                timestamp = datetime.datetime.fromisoformat(str(event["timestamp"]))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=datetime.UTC)
            except (KeyError, TypeError, ValueError):
                continue
            values = stats.setdefault(
                carrier_id,
                {
                    "delivered_total": 0,
                    "delivered_week": 0,
                    "delivered_month": 0,
                    "delivered_year": 0,
                },
            )
            values["delivered_total"] += 1
            if timestamp >= start_week:
                values["delivered_week"] += 1
            if timestamp >= start_month:
                values["delivered_month"] += 1
            if timestamp >= start_year:
                values["delivered_year"] += 1
        total = {
            "delivered_total": 0,
            "delivered_week": 0,
            "delivered_month": 0,
            "delivered_year": 0,
        }
        for values in stats.values():
            for key in total:
                total[key] += values[key]
        stats["__all__"] = total
        return stats

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
                barcode = _normalize_code(parcel.get("barcode"))
                fallback = _stable_direct_parcel_key(parcel, carrier)
                parcel_id = f"direct:{carrier.casefold()}:{barcode or fallback}"
                parcel.update(
                    {
                        "id": parcel_id,
                        "carrier_id": carrier.casefold().replace(" ", "_"),
                        "barcode": barcode,
                        "tracking_url": parcel.get("tracking_url")
                        or _build_tracking_url(
                            barcode,
                            self.entry.options.get(CONF_CARRIERS, {}).get(
                                carrier.casefold().replace(" ", "_"), {}
                            ),
                            self.entry.options.get(CONF_POSTAL_CODE, ""),
                        ),
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
                barcode = _normalize_code(parcel.get("barcode"))
                dedupe_key = f"barcode:{barcode}" if barcode else parcel["id"]
                merged[dedupe_key] = parcel

        for parcel in self._direct_parcels():
            barcode = _normalize_code(parcel.get("barcode"))
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
        stale_cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
            hours=48
        )
        stale = 0
        pickup = 0
        for parcel in parcels:
            if parcel.get("pickup") or parcel.get("status") == "at_pickup_point":
                pickup += 1
            try:
                last_seen = datetime.datetime.fromisoformat(
                    str(parcel.get("last_seen"))
                )
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=datetime.UTC)
                if (
                    parcel.get("status") not in {"delivered", "problem"}
                    and last_seen < stale_cutoff
                ):
                    stale += 1
            except (TypeError, ValueError):
                continue
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
            "stale": stale,
            "pickup": pickup,
            "parcels": parcels,
        }

    async def async_confirm_received(self) -> int:
        """Verberg alle huidige pakketten en bewaar tombstones tegen herdetectie."""
        summary = (self.data or {}).get(SUMMARY_KEY, {})
        parcels = summary.get("parcels", [])
        if not parcels:
            return 0
        confirmed = self._cache.setdefault("confirmed", {})
        events = self._cache.setdefault("delivery_events", [])
        if not isinstance(events, list):
            events = []
            self._cache["delivery_events"] = events
        now = datetime.datetime.now(datetime.UTC).isoformat()
        for parcel in parcels:
            barcode = _normalize_code(parcel.get("barcode"))
            event_id = f"barcode:{barcode}" if barcode else parcel.get("id")
            already_confirmed = bool(event_id and event_id in confirmed)
            if parcel_id := parcel.get("id"):
                confirmed[parcel_id] = now
            if barcode:
                confirmed[f"barcode:{barcode}"] = now
            if event_id and not already_confirmed:
                events.append(
                    {
                        "id": event_id,
                        "carrier_id": parcel.get("carrier_id") or "unknown",
                        "timestamp": now,
                    }
                )
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
        detail_lines = [
            f"- {parcel.get('carrier') or 'Onbekend'}: "
            f"{str(parcel.get('status') or 'onbekend').replace('_', ' ')}"
            for parcel in parcels[:5]
        ]
        if len(parcels) > 5:
            detail_lines.append(f"- en nog {len(parcels) - 5}")
        detail_text = "\n".join(detail_lines)
        confirm_action = f"PAKKET_TRACKER_CONFIRM_{self.entry.entry_id}"
        keep_action = f"PAKKET_TRACKER_KEEP_{self.entry.entry_id}"
        await self.hass.services.async_call(
            domain,
            service,
            {
                "title": "📦 Zijn alle pakketten ontvangen?",
                "message": (
                    f"Er staan {len(parcels)} pakket(ten) open ({status_text}). "
                    f"\n{detail_text}\nZijn alle verwachte bezorgingen binnen?"
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
