"""Sensor-platform voor Pakket Tracker NL.

Maakt per geconfigureerde vervoerder statussensoren aan voor registered,
transit, delivering, delivered, packages en missed. Alle sensoren van een config entry
worden gegroepeerd onder één device in de HA-UI.
"""

from __future__ import annotations

from homeassistant.components.sensor import RestoreSensor, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CARRIER_NAME,
    CONF_CARRIERS,
    CONF_USERNAME,
    DOMAIN,
    SUMMARY_KEY,
    VERSION,
)

ICONS = {
    "registered": "mdi:package-variant-plus",
    "transit": "mdi:truck-outline",
    "delivering": "mdi:truck-delivery",
    "delivered": "mdi:package-variant",
    "packages": "mdi:package-variant-closed",
    "missed": "mdi:truck-alert",
}

STAT_LABELS = {
    "registered": "Registered",
    "transit": "In Transit",
    "delivering": "Delivering",
    "delivered": "Delivered",
    "packages": "Packages",
    "missed": "Missed",
}

SUMMARY_SENSORS = {
    "active": ("Pakket Tracker Actieve pakketten", "mdi:package-variant-closed"),
    "out_for_delivery": ("Pakket Tracker Vandaag onderweg", "mdi:truck-fast"),
    "delivered_unconfirmed": (
        "Pakket Tracker Bezorgd onbevestigd",
        "mdi:package-check",
    ),
    "problems": ("Pakket Tracker Problemen", "mdi:package-variant-remove"),
    "total": ("Pakket Tracker Totaal open", "mdi:package-variant"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    carriers: dict[str, dict] = entry.options.get(CONF_CARRIERS, {})

    entities: list[PakketTrackerSensor] = []
    for carrier_id, rule in carriers.items():
        carrier_name = rule.get(CARRIER_NAME, carrier_id)
        for stat in (
            "registered",
            "transit",
            "delivering",
            "delivered",
            "packages",
            "missed",
        ):
            entities.append(
                PakketTrackerSensor(coordinator, entry, carrier_id, carrier_name, stat)
            )
    for summary_key, (name, icon) in SUMMARY_SENSORS.items():
        entities.append(
            PakketTrackerSummarySensor(coordinator, entry, summary_key, name, icon)
        )
    async_add_entities(entities)


class PakketTrackerSensor(CoordinatorEntity, RestoreSensor):
    """Eén statistiek (delivering/delivered/packages/missed) van één vervoerder."""

    _attr_native_unit_of_measurement = "package(s)"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        carrier_id: str,
        carrier_name: str,
        stat: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._username = entry.data.get(CONF_USERNAME, "")
        self._carrier_id = carrier_id
        self._stat = stat
        self._attr_unique_id = f"{entry.entry_id}_{carrier_id}_{stat}"
        self._attr_name = f"{carrier_name} {STAT_LABELS[stat]}"
        self._attr_icon = ICONS.get(stat, "mdi:package")

    async def async_added_to_hass(self) -> None:
        """Herstel de vorige waarde totdat de eerste achtergrondscan klaar is."""
        await super().async_added_to_hass()
        if (sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = sensor_data.native_value

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if data is None:
            return getattr(self, "_attr_native_value", None)
        value = data.get(self._carrier_id, {}).get(self._stat)
        if value is not None:
            self._attr_native_value = value
        return getattr(self, "_attr_native_value", None)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Toon gevonden trackingcodes zonder de bestaande state te wijzigen."""
        data = self.coordinator.data or {}
        carrier = data.get(self._carrier_id, {})
        tracking = carrier.get("tracking", {}).get(self._stat, [])
        return {
            "tracking_codes": tracking,
            "last_scan_success": self.coordinator.last_update_success,
        }

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": (
                f"Pakket Tracker ({self._username})"
                if self._username
                else "Pakket Tracker NL"
            ),
            "manufacturer": "Pakket Tracker Community",
            "model": "IMAP Pakket Monitor",
            "sw_version": VERSION,
        }


class PakketTrackerSummarySensor(CoordinatorEntity, RestoreSensor):
    """Eén centrale sensor over mail- en directe vervoerderbronnen."""

    _attr_native_unit_of_measurement = "package(s)"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        summary_key: str,
        name: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._username = entry.data.get(CONF_USERNAME, "")
        self._summary_key = summary_key
        self._attr_unique_id = f"{entry.entry_id}_summary_{summary_key}"
        self._attr_name = name
        self._attr_icon = icon

    async def async_added_to_hass(self) -> None:
        """Herstel de vorige samenvatting tot de eerste scan gereed is."""
        await super().async_added_to_hass()
        if (sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = sensor_data.native_value

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if data is None:
            return getattr(self, "_attr_native_value", None)
        value = data.get(SUMMARY_KEY, {}).get(self._summary_key)
        if value is not None:
            self._attr_native_value = value
        return getattr(self, "_attr_native_value", None)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Lever de canonieke pakketlijst en uitsplitsing per vervoerder."""
        data = self.coordinator.data or {}
        summary = data.get(SUMMARY_KEY, {})
        by_carrier = {
            carrier_id: values.get("packages", 0)
            for carrier_id, values in data.items()
            if carrier_id != SUMMARY_KEY and isinstance(values, dict)
        }
        attributes: dict[str, object] = {
            "by_carrier": by_carrier,
            "last_scan_success": self.coordinator.last_update_success,
        }
        # Eén canonieke lijst voorkomt dat dezelfde grote attributen vijf keer
        # in Recorder terechtkomen. De andere sensoren blijven lichte tellers.
        if self._summary_key == "total":
            attributes["parcels"] = summary.get("parcels", [])
        return attributes

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": (
                f"Pakket Tracker ({self._username})"
                if self._username
                else "Pakket Tracker NL"
            ),
            "manufacturer": "Pakket Tracker Community",
            "model": "Unified Parcel Registry",
            "sw_version": VERSION,
        }
