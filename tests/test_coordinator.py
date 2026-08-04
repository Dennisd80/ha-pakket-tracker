"""Tests voor coordinator-integraties."""

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pakket_tracker.const import DOMAIN
from custom_components.pakket_tracker.coordinator import PakketTrackerCoordinator


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
