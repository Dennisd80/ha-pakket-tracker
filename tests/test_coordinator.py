"""Tests voor coordinator-integraties."""

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
)


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
