"""Tests voor pure parsing- en classificatiehelpers."""

import datetime
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.sensor import SensorStateClass

from custom_components.pakket_tracker import (
    _parse_confirmation_time,
    _upgrade_preset_options,
)
from custom_components.pakket_tracker.config_flow import _split_regex_lines
from custom_components.pakket_tracker.const import (
    CARRIER_DELIVERED_SUBJECTS,
    CARRIER_DELIVERING_SUBJECTS,
    CARRIER_MISSED_SUBJECTS,
    CARRIER_NAME,
    CARRIER_REGISTERED_SUBJECTS,
    CARRIER_SENDERS,
    CARRIER_TRANSIT_SUBJECTS,
    CONF_CARRIERS,
    CONF_PRESET_VERSION,
    PRESET_CARRIERS,
    PRESET_VERSION,
)
from custom_components.pakket_tracker.coordinator import (
    PakketTrackerCoordinator,
    _build_tracking_url,
    _classify_messages,
    _extract_tracking_code,
    _normalize_code,
    _parse_message,
    _sender_matches,
    _stable_direct_parcel_key,
    _threading_diagnostics,
)
from custom_components.pakket_tracker.sensor import (
    PakketTrackerSensor,
    PakketTrackerSummarySensor,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("07:30", (7, 30, 0)), ("22:00:15", (22, 0, 15))],
)
def test_parse_confirmation_time(value, expected):
    assert _parse_confirmation_time(value) == expected


def test_count_sensors_enable_measurement_statistics():
    coordinator = Mock()
    entry = SimpleNamespace(entry_id="test-entry", data={})
    carrier_sensor = PakketTrackerSensor(
        coordinator,
        entry,
        "voorbeeld",
        "Voorbeeld",
        "packages",
    )
    summary_sensor = PakketTrackerSummarySensor(
        coordinator,
        entry,
        "total",
        "Pakket Tracker Totaal open",
        "mdi:package",
    )

    assert carrier_sensor.state_class is SensorStateClass.MEASUREMENT
    assert summary_sensor.state_class is SensorStateClass.MEASUREMENT


@pytest.mark.parametrize("value", ["", "24:00", "12:60", "12", "12:00:00:00"])
def test_parse_confirmation_time_rejects_invalid_values(value):
    with pytest.raises((TypeError, ValueError)):
        _parse_confirmation_time(value)


def test_sender_matching_is_exact_and_supports_domains():
    assert _sender_matches(["pakket@example.com"], ["pakket@example.com"])
    assert not _sender_matches(["pakket@example.com"], ["nep@example.com"])
    assert _sender_matches(["@example.com"], ["pakket@example.com"])


def test_extract_tracking_code():
    assert _extract_tracking_code("Je barcode is 3SABCDEFGHIJKL") == "3SABCDEFGHIJKL"
    assert _extract_tracking_code("Je afspraak is op 20260804") is None


def test_build_tracking_url_uses_code_and_optional_postal_code():
    assert _build_tracking_url(
        "3SABC123",
        {"tracking_url": "https://example.test/{code}?pc={postal_code}"},
        "3146 CH",
    ) == "https://example.test/3SABC123?pc=3146%20CH"


@pytest.mark.parametrize(
    "template",
    ["https://example.test/{}", "https://example.test/{code.upper}"],
)
def test_build_tracking_url_rejects_unsafe_templates(template):
    assert _build_tracking_url("ABC123", {"tracking_url": template}) is None


def test_delivery_statistics_uses_local_timezone_boundaries():
    now = datetime.datetime.now(datetime.UTC)
    coordinator = SimpleNamespace(
        _cache={
            "delivery_events": [
                {
                    "id": "barcode:ABC123",
                    "carrier_id": "postnl",
                    "timestamp": now.isoformat(),
                }
            ],
            "delivered_totals": {"postnl": 1},
        }
    )
    stats = PakketTrackerCoordinator._delivery_statistics(
        coordinator, ZoneInfo("Europe/Amsterdam")
    )
    assert stats["postnl"] == {
        "delivered_total": 1,
        "delivered_week": 1,
        "delivered_month": 1,
        "delivered_year": 1,
    }


def test_tracking_code_normalization_removes_spaces_and_hyphens():
    assert _normalize_code(" 3s-abc 123 ") == "3SABC123"
    assert (
        _extract_tracking_code(
            "barcode: 3s-abc 123",
            [r"barcode:\s*([a-z0-9 -]{8,})"],
        )
        == "3SABC123"
    )


def test_broad_numeric_tracking_pattern_requires_context():
    assert _extract_tracking_code(
        "Order 123456789012 placed", [r"\b(\d{12})\b"]
    ) is None
    assert _extract_tracking_code(
        "tracking number 123456789012", [r"\b(\d{12})\b"]
    ) == "123456789012"


def test_direct_parcel_fallback_ignores_status_changes():
    base = {
        "carrier": "Voorbeeld",
        "sender": "Winkel",
        "title": "Bestelling",
        "status": "in_transit",
    }
    changed = {**base, "status": "delivered"}
    assert _stable_direct_parcel_key(base, "Voorbeeld") == _stable_direct_parcel_key(
        changed, "Voorbeeld"
    )


def test_parse_message_uses_thread_root_from_references():
    parsed = _parse_message(
        "3",
        b"From: pakket@example.com\r\n"
        b"Subject: Bezorgd\r\n"
        b"Message-ID: <third@example.com>\r\n"
        b"References: <root@example.com> <second@example.com>\r\n"
        b"In-Reply-To: <second@example.com>\r\n"
        b"\r\nJe pakket is bezorgd.",
    )

    assert parsed["message_id"] == "<third@example.com>"
    assert parsed["thread_id"] == "<root@example.com>"


def test_tracking_regex_input_preserves_case_and_escapes():
    assert _split_regex_lines("\\D+\n[A-Z]{2}") == ["\\D+", "[A-Z]{2}"]


@pytest.mark.parametrize(
    ("carrier_id", "sender", "subject", "tracking_code", "status"),
    [
        (
            "bolcom",
            "noreply@bol.com",
            "Je bestelling is onderweg",
            "3SABCDEFGHIJKL",
            "transit",
        ),
        (
            "aliexpress",
            "transaction@notice.aliexpress.com",
            "Your package has been delivered",
            "LP123456789CN",
            "delivered",
        ),
        (
            "usps",
            "auto-reply@tracking.usps.com",
            "Out for Delivery",
            "9400111899223856928499",
            "delivering",
        ),
        (
            "ups",
            "pkginfo@ups.com",
            "Your UPS Package was delivered",
            "1Z999AA10123456784",
            "delivered",
        ),
        (
            "fedex",
            "trackingupdates@fedex.com",
            "FedEx Delivery Exception",
            "123456789012",
            "missed",
        ),
    ],
)
def test_new_preset_carriers_are_classified(
    carrier_id, sender, subject, tracking_code, status
):
    result = _classify_messages(
        [
            {
                "uid": "1",
                "senders": [sender],
                "subject": subject.casefold(),
                "body": f"tracking number: {tracking_code}".casefold(),
                "message_id": f"{carrier_id}@example.com",
                "timestamp": 1.0,
            }
        ],
        {carrier_id: PRESET_CARRIERS[carrier_id]},
    )

    assert result[carrier_id]["packages"] == 1
    assert result[carrier_id][status] == 1
    assert result[carrier_id]["tracking"][status] == [tracking_code]


def test_carrier_status_text_from_wrong_sender_is_ignored():
    result = _classify_messages(
        [
            {
                "uid": "1",
                "senders": ["phishing@example.com"],
                "subject": "your package has been delivered",
                "body": "tracking number: 123456789012",
                "message_id": "wrong-sender@example.com",
                "timestamp": 1.0,
            }
        ],
        {"fedex": PRESET_CARRIERS["fedex"]},
    )

    assert result["fedex"]["packages"] == 0


def test_trunkrs_sequence_updates_one_package_to_delivered():
    tracking_code = "987654321"
    messages = [
        {
            "uid": "1",
            "senders": ["noreply@trunkrs.nl"],
            "subject": f"Bevestiging aanmelding pakket: [{tracking_code}]",
            "body": "Je pakket is aangemeld en nog niet fysiek ontvangen",
            "message_id": "trunkrs-registered@example.com",
            "timestamp": 1.0,
        },
        {
            "uid": "2",
            "senders": ["noreply@trunkrs.nl"],
            "subject": f"Bevestiging in sorteercentrum: [{tracking_code}]",
            "body": "Je pakket is aangekomen in ons sorteercentrum",
            "message_id": "trunkrs-transit@example.com",
            "timestamp": 2.0,
        },
        {
            "uid": "3",
            "senders": ["noreply@trunkrs.nl"],
            "subject": f"Afgeleverd: [{tracking_code}]",
            "body": "Je pakket is succesvol afgeleverd",
            "message_id": "trunkrs-delivered@example.com",
            "timestamp": 3.0,
        },
    ]

    result = _classify_messages(
        messages,
        {"trunkrs": PRESET_CARRIERS["trunkrs"]},
    )["trunkrs"]

    assert result["packages"] == 1
    assert result["registered"] == 0
    assert result["transit"] == 0
    assert result["delivered"] == 1
    assert result["tracking"]["delivered"] == [tracking_code]


def test_budbee_evening_delivery_is_out_for_delivery():
    result = _classify_messages(
        [
            {
                "uid": "1",
                "senders": ["no-reply@budbee.com"],
                "subject": "Vandaag bezorgd",
                "body": (
                    "Je bestelling wordt vanavond bezorgd. "
                    "We komen langs tussen 14:00 en 19:00."
                ),
                "message_id": "budbee@example.com",
                "timestamp": 1.0,
            }
        ],
        {"budbee": PRESET_CARRIERS["budbee"]},
    )["budbee"]

    assert result["packages"] == 1
    assert result["delivering"] == 1


def test_amazon_tomorrow_delivery_has_planned_local_date():
    mail_time = datetime.datetime(
        2026, 8, 7, 21, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=2))
    )
    result = _classify_messages(
        [
            {
                "uid": "1",
                "senders": ["verzending-volgen@amazon.nl"],
                "subject": "Je bestelling wordt morgen bezorgd",
                "body": "Volg je bestelling wanneer deze onderweg voor bezorging is.",
                "message_id": "amazon-tomorrow@example.com",
                "timestamp": mail_time.timestamp(),
            }
        ],
        {"amazon_nl": PRESET_CARRIERS["amazon_nl"]},
        time_zone=mail_time.tzinfo,
    )["amazon_nl"]

    assert result["packages"] == 1
    assert result["transit"] == 1
    assert result["delivering"] == 0
    assert result["parcels"][0]["planned_from"] == "2026-08-08T00:00:00+02:00"
    assert result["parcels"][0]["planned_to"].startswith(
        "2026-08-08T23:59:59.999999+02:00"
    )


def test_preset_upgrade_is_one_time_and_preserves_custom_values():
    postnl = deepcopy(PRESET_CARRIERS["postnl"])
    postnl[CARRIER_NAME] = "Mijn PostNL"
    postnl[CARRIER_SENDERS] = ["custom@example.com"]
    options = {CONF_CARRIERS: {"postnl": postnl}}

    upgraded = _upgrade_preset_options(options)

    assert upgraded is not None
    assert upgraded[CONF_PRESET_VERSION] == PRESET_VERSION
    assert upgraded[CONF_CARRIERS]["postnl"][CARRIER_NAME] == "Mijn PostNL"
    assert "custom@example.com" in upgraded[CONF_CARRIERS]["postnl"][CARRIER_SENDERS]
    assert upgraded[CONF_CARRIERS]["postnl"]["tracking_url"]
    assert set(PRESET_CARRIERS) <= set(upgraded[CONF_CARRIERS])
    assert _upgrade_preset_options(upgraded) is None


def test_classification_prefers_latest_status_for_tracking_code():
    carriers = {
        "voorbeeld": {
            CARRIER_NAME: "Voorbeeld",
            CARRIER_SENDERS: ["pakket@example.com"],
            CARRIER_DELIVERING_SUBJECTS: ["vandaag onderweg"],
            CARRIER_DELIVERED_SUBJECTS: ["is bezorgd"],
            CARRIER_MISSED_SUBJECTS: ["bezorging gemist"],
        }
    }
    messages = [
        {
            "uid": "1",
            "senders": ["pakket@example.com"],
            "subject": "vandaag onderweg",
            "body": "barcode: 3SABCDEFGHIJKL",
            "message_id": "onderweg@example.com",
            "timestamp": 1.0,
        },
        {
            "uid": "2",
            "senders": ["pakket@example.com"],
            "subject": "is bezorgd",
            "body": "barcode: 3SABCDEFGHIJKL",
            "message_id": "bezorgd@example.com",
            "timestamp": 2.0,
        },
    ]

    result = _classify_messages(messages, carriers)

    assert result["voorbeeld"]["packages"] == 1
    assert result["voorbeeld"]["delivered"] == 1
    assert result["voorbeeld"]["delivering"] == 0


def test_threaded_status_messages_without_barcode_form_one_package():
    carriers = {
        "voorbeeld": {
            CARRIER_NAME: "Voorbeeld",
            CARRIER_SENDERS: ["pakket@example.com"],
            CARRIER_REGISTERED_SUBJECTS: ["aangemeld"],
            CARRIER_TRANSIT_SUBJECTS: ["onderweg"],
            CARRIER_DELIVERED_SUBJECTS: ["bezorgd"],
        }
    }
    messages = [
        {
            "uid": str(index),
            "senders": ["pakket@example.com"],
            "subject": subject,
            "body": "",
            "message_id": f"<status-{index}@example.com>",
            "thread_id": "<root@example.com>",
            "timestamp": float(index),
        }
        for index, subject in enumerate(
            ("pakket aangemeld", "pakket onderweg", "pakket bezorgd"), start=1
        )
    ]

    result = _classify_messages(messages, carriers)["voorbeeld"]

    assert result["packages"] == 1
    assert result["registered"] == 0
    assert result["transit"] == 0
    assert result["delivered"] == 1


def test_thread_first_without_barcode_merges_with_later_barcode():
    carriers = {
        "voorbeeld": {
            CARRIER_NAME: "Voorbeeld",
            CARRIER_SENDERS: ["pakket@example.com"],
            CARRIER_TRANSIT_SUBJECTS: ["onderweg"],
            CARRIER_DELIVERED_SUBJECTS: ["bezorgd"],
        }
    }
    messages = [
        {
            "uid": "1",
            "senders": ["pakket@example.com"],
            "subject": "pakket onderweg",
            "body": "",
            "message_id": "<first@example.com>",
            "thread_id": "<root@example.com>",
            "timestamp": 1.0,
        },
        {
            "uid": "2",
            "senders": ["pakket@example.com"],
            "subject": "pakket bezorgd",
            "body": "barcode: 3SABCDEFGHIJKL",
            "message_id": "<second@example.com>",
            "thread_id": "<root@example.com>",
            "timestamp": 2.0,
        },
    ]
    result = _classify_messages(messages, carriers)["voorbeeld"]
    assert result["packages"] == 1
    assert result["delivered"] == 1
    assert result["tracking"]["delivered"] == ["3SABCDEFGHIJKL"]


def test_threading_diagnostics_only_returns_aggregate_counts():
    messages = [
        {
            "uid": "1",
            "senders": ["pakket@example.com"],
            "subject": "pakket onderweg",
            "body": "barcode: 3SABCDEFGHIJKL",
            "message_id": "<root@example.com>",
            "thread_id": "<root@example.com>",
        },
        {
            "uid": "2",
            "senders": ["pakket@example.com"],
            "subject": "pakket bezorgd",
            "body": "barcode: 3SZYXWVUTSRQP",
            "message_id": "<reply@example.com>",
            "thread_id": "<root@example.com>",
        },
    ]
    carriers = {
        "voorbeeld": {
            CARRIER_SENDERS: ["pakket@example.com"],
            CARRIER_TRANSIT_SUBJECTS: ["onderweg"],
            CARRIER_DELIVERED_SUBJECTS: ["bezorgd"],
        }
    }

    result = _threading_diagnostics(messages, carriers)

    assert result == {
        "voorbeeld": {
            "recognized_status_messages": 2,
            "messages_with_thread_relation": 1,
            "multi_message_thread_groups": 1,
            "thread_groups_with_multiple_tracking_codes": 1,
        }
    }
