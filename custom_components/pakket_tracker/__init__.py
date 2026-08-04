"""Pakket Tracker NL -- eigen IMAP-gebaseerde pakkettracker voor NL vervoerders."""

from __future__ import annotations

from copy import deepcopy

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change

from .const import (
    ATTR_ENTRY_ID,
    CARRIER_DELIVERED_SUBJECTS,
    CARRIER_DELIVERING_SUBJECTS,
    CARRIER_MISSED_SUBJECTS,
    CARRIER_REGISTERED_SUBJECTS,
    CARRIER_SENDERS,
    CARRIER_TRACKING_PATTERNS,
    CARRIER_TRANSIT_SUBJECTS,
    CONF_CARRIERS,
    CONF_CONFIRMATION_ENABLED,
    CONF_CONFIRMATION_TIME,
    CONF_PRESET_VERSION,
    DEFAULT_CONFIRMATION_ENABLED,
    DEFAULT_CONFIRMATION_TIME,
    DOMAIN,
    PRESET_CARRIERS,
    PRESET_VERSION,
    SERVICE_CONFIRM_RECEIVED,
    SERVICE_KEEP_PARCELS,
)
from .coordinator import PakketTrackerCoordinator

PLATFORMS: list[str] = ["sensor"]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_MERGED_CARRIER_LIST_FIELDS = (
    CARRIER_SENDERS,
    CARRIER_REGISTERED_SUBJECTS,
    CARRIER_TRANSIT_SUBJECTS,
    CARRIER_DELIVERING_SUBJECTS,
    CARRIER_DELIVERED_SUBJECTS,
    CARRIER_MISSED_SUBJECTS,
    CARRIER_TRACKING_PATTERNS,
)


def _upgrade_preset_options(options: dict) -> dict | None:
    """Voeg nieuwe presetregels één keer toe zonder gebruikersnamen te wijzigen."""
    try:
        installed_version = int(options.get(CONF_PRESET_VERSION, 1))
    except (TypeError, ValueError):
        installed_version = 1
    if installed_version >= PRESET_VERSION:
        return None

    upgraded = deepcopy(options)
    carriers = deepcopy(dict(upgraded.get(CONF_CARRIERS, {})))
    for carrier_id, preset in PRESET_CARRIERS.items():
        if carrier_id not in carriers:
            carriers[carrier_id] = deepcopy(preset)
            continue
        carrier = carriers[carrier_id]
        for field in _MERGED_CARRIER_LIST_FIELDS:
            existing = list(carrier.get(field, []))
            carrier[field] = existing + [
                value for value in preset.get(field, []) if value not in existing
            ]

    upgraded[CONF_CARRIERS] = carriers
    upgraded[CONF_PRESET_VERSION] = PRESET_VERSION
    return upgraded


def _parse_confirmation_time(value: str) -> tuple[int, int, int]:
    """Parseer HH:MM of HH:MM:SS zonder een geldige tijd te verschuiven."""
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        parts.append(0)
    if (
        len(parts) != 3
        or not 0 <= parts[0] <= 23
        or not 0 <= parts[1] <= 59
        or not 0 <= parts[2] <= 59
    ):
        raise ValueError("Ongeldige bevestigingstijd")
    return parts[0], parts[1], parts[2]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Registreer centrale acties voor alle Pakket Tracker-accounts."""
    hass.data.setdefault(DOMAIN, {})

    async def _coordinators(call: ServiceCall) -> list[PakketTrackerCoordinator]:
        entry_id = call.data.get(ATTR_ENTRY_ID)
        return [
            coordinator
            for key, coordinator in hass.data.get(DOMAIN, {}).items()
            if isinstance(coordinator, PakketTrackerCoordinator)
            and (not entry_id or key == entry_id)
        ]

    async def _confirm_received(call: ServiceCall) -> None:
        for coordinator in await _coordinators(call):
            await coordinator.async_confirm_received()

    async def _keep_parcels(call: ServiceCall) -> None:
        """Bewust geen mutatie: open pakketten blijven zichtbaar."""
        return None

    hass.services.async_register(DOMAIN, SERVICE_CONFIRM_RECEIVED, _confirm_received)
    hass.services.async_register(DOMAIN, SERVICE_KEEP_PARCELS, _keep_parcels)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Zet een config entry op zonder de HA-opstart op IMAP te laten wachten."""
    if (upgraded_options := _upgrade_preset_options(dict(entry.options))) is not None:
        hass.config_entries.async_update_entry(entry, options=upgraded_options)

    coordinator = PakketTrackerCoordinator(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    confirmation_time = entry.options.get(
        CONF_CONFIRMATION_TIME, DEFAULT_CONFIRMATION_TIME
    )
    try:
        hour, minute, second = _parse_confirmation_time(confirmation_time)
    except (AttributeError, TypeError, ValueError):
        hour, minute, second = 22, 0, 0

    async def _daily_confirmation(_now) -> None:
        if entry.options.get(CONF_CONFIRMATION_ENABLED, DEFAULT_CONFIRMATION_ENABLED):
            await coordinator.async_send_confirmation_notification()

    entry.async_on_unload(
        async_track_time_change(
            hass,
            _daily_confirmation,
            hour=hour,
            minute=minute,
            second=second,
        )
    )

    async def _notification_action(event: Event) -> None:
        action = event.data.get("action")
        if action == f"PAKKET_TRACKER_CONFIRM_{entry.entry_id}":
            await coordinator.async_confirm_received()
        elif action == f"PAKKET_TRACKER_KEEP_{entry.entry_id}":
            return

    entry.async_on_unload(
        hass.bus.async_listen("mobile_app_notification_action", _notification_action)
    )

    # Een trage of onbereikbare mailbox mag de startup-fase niet blokkeren.
    entry.async_create_background_task(
        hass,
        coordinator.async_refresh(),
        f"{DOMAIN}_initial_refresh",
    )
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Herlaad de integratie zodra de vervoerders-configuratie wijzigt."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Ontlaad een config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
