"""Tests voor coordinator-integraties."""

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pakket_tracker.const import (
    CARRIER_DELIVERING_SUBJECTS,
    CARRIER_NAME,
    CARRIER_SENDERS,
    CARRIER_TRACKING_PATTERNS,
    DOMAIN,
)
from custom_components.pakket_tracker.coordinator import (
    PakketTrackerCoordinator,
    _classify_messages,
    _fetch_recent_emails,
)


class _FakeImap:
    def __init__(self):
        self.fetch_calls = []

    def login(self, _username, _password):
        return "OK", []

    def select(self, _folder, readonly=True):
        return "OK", []

    def status(self, _folder, _query):
        return "OK", [b"* STATUS INBOX (UIDVALIDITY 42)"]

    def uid(self, command, *args):
        if command == "search":
            return "OK", [b"1 2"]
        if command == "fetch":
            self.fetch_calls.append(args)
            if args[0] == "1,2":
                return "OK", [
                    (
                        b"1 (UID 1 BODY[] {64})",
                        b"From: a@example.com\r\nSubject: One\r\n\r\n",
                    ),
                    (
                        b"2 (UID 2 BODY[] {64})",
                        b"From: b@example.com\r\nSubject: Two\r\n\r\n",
                    ),
                ]
        return "NO", []

    def logout(self):
        return "OK", []


def test_fetch_recent_emails_uses_one_batch_fetch(monkeypatch):
    fake = _FakeImap()
    monkeypatch.setattr(
        "custom_components.pakket_tracker.coordinator.imaplib.IMAP4_SSL",
        lambda *args, **kwargs: fake,
    )
    data = {
        "imap_server": "imap.example.com",
        "imap_port": 993,
        "imap_ssl": True,
        "username": "user@example.com",
        "password": "secret",
        "folder": "INBOX",
        "scan_window_days": 2,
    }

    messages, _cache, fetched = _fetch_recent_emails(data, {})

    assert fetched == 2
    assert len(messages) == 2
    assert [call[0] for call in fake.fetch_calls] == ["1,2"]


@pytest.mark.asyncio
async def test_scan_errors_raise_after_three_consecutive_failures(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    coordinator = PakketTrackerCoordinator(hass, entry)
    coordinator._cache_loaded = True
    coordinator.data = {}

    def fail_scan(*_args):
        raise OSError("mailbox unavailable")

    monkeypatch.setattr(
        "custom_components.pakket_tracker.coordinator._fetch_recent_emails",
        fail_scan,
    )

    await coordinator._async_update_data()
    await coordinator._async_update_data()
    with pytest.raises(Exception, match="IMAP-scan mislukt"):
        await coordinator._async_update_data()
    assert coordinator.consecutive_scan_failures == 3
    assert coordinator.last_scan_error == "mailbox unavailable"


def test_parcel_aggregator_entity_can_be_renamed(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    registry = er.async_get(hass)
    registry_entry = registry.async_get_or_create(
        "sensor",
        "parcel_aggregator",
        "parcel_aggregator_incoming",
        suggested_object_id="mijn_hernoemde_pakketten",
    )
    hass.states.async_set(
        registry_entry.entity_id,
        1,
        {
            "parcels": [
                {
                    "carrier": "Voorbeeld",
                    "barcode": "TRACK12345678",
                    "status": "in_transit",
                }
            ]
        },
    )

    coordinator = PakketTrackerCoordinator(hass, entry)
    parcels = coordinator._direct_parcels()

    assert len(parcels) == 1
    assert parcels[0]["barcode"] == "TRACK12345678"
    assert parcels[0]["source"] == "parcel_aggregator"


def test_mail_and_direct_barcode_variants_are_merged(hass):
    carriers = {
        "voorbeeld": {
            CARRIER_NAME: "Voorbeeld",
            CARRIER_SENDERS: ["pakket@example.com"],
            CARRIER_DELIVERING_SUBJECTS: ["onderweg"],
            CARRIER_TRACKING_PATTERNS: [r"barcode:\s*([a-z0-9 -]{8,})"],
        }
    }
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    registry = er.async_get(hass)
    registry_entry = registry.async_get_or_create(
        "sensor",
        "parcel_aggregator",
        "parcel_aggregator_incoming",
        suggested_object_id="parcel_aggregator_incoming_parcels",
    )
    hass.states.async_set(
        registry_entry.entity_id,
        1,
        {
            "parcels": [
                {
                    "carrier": "Voorbeeld",
                    "barcode": "3S-ABC-123",
                    "status": "in_transit",
                }
            ]
        },
    )
    email_result = _classify_messages(
        [
            {
                "uid": "1",
                "senders": ["pakket@example.com"],
                "subject": "pakket onderweg",
                "body": "barcode: 3SABC 123",
                "message_id": "<mail@example.com>",
                "timestamp": 1.0,
            }
        ],
        carriers,
    )

    coordinator = PakketTrackerCoordinator(hass, entry)
    summary = coordinator._build_summary(email_result, set())

    assert summary["total"] == 1
    assert summary["parcels"][0]["barcode"] == "3SABC123"
