"""Veilige diagnostiek voor Pakket Tracker NL."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_NOTIFY_SERVICE, CONF_PASSWORD, CONF_USERNAME, DOMAIN

_TO_REDACT = {CONF_NOTIFY_SERVICE, CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Lever configuratie en coordinatorstatus zonder geheimen of mailinhoud."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    cache_messages = coordinator._cache.get("messages", {})  # noqa: SLF001
    carrier_counts = {
        carrier_id: {
            key: value
            for key, value in values.items()
            if key in {"delivering", "delivered", "packages", "missed"}
        }
        for carrier_id, values in (coordinator.data or {}).items()
        if carrier_id != "_summary"
    }
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), _TO_REDACT),
            "options": async_redact_data(dict(entry.options), _TO_REDACT),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": (
                str(coordinator.last_exception)
                if coordinator.last_exception is not None
                else None
            ),
            "cached_message_count": (
                len(cache_messages) if isinstance(cache_messages, dict) else 0
            ),
            "carrier_counts": carrier_counts,
        },
    }
