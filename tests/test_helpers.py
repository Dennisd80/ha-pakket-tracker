"""Tests voor pure parsing- en classificatiehelpers."""

import pytest

from custom_components.pakket_tracker import _parse_confirmation_time
from custom_components.pakket_tracker.const import (
    CARRIER_DELIVERED_SUBJECTS,
    CARRIER_DELIVERING_SUBJECTS,
    CARRIER_MISSED_SUBJECTS,
    CARRIER_NAME,
    CARRIER_SENDERS,
)
from custom_components.pakket_tracker.coordinator import (
    _classify_messages,
    _extract_tracking_code,
    _sender_matches,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("07:30", (7, 30, 0)), ("22:00:15", (22, 0, 15))],
)
def test_parse_confirmation_time(value, expected):
    assert _parse_confirmation_time(value) == expected


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
