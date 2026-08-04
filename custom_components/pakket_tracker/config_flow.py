"""Config flow voor Pakket Tracker NL.

- ConfigFlow: eenmalige koppeling met het IMAP-account.
- OptionsFlow: vervoerders toevoegen / bewerken / verwijderen, en de
  scan-interval aanpassen.
"""

from __future__ import annotations

import imaplib
import logging
import re
from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CARRIER_DELIVERED_SUBJECTS,
    CARRIER_DELIVERING_SUBJECTS,
    CARRIER_MISSED_SUBJECTS,
    CARRIER_NAME,
    CARRIER_REGISTERED_SUBJECTS,
    CARRIER_SENDERS,
    CARRIER_TRACKING_PATTERNS,
    CARRIER_TRANSIT_SUBJECTS,
    CONF_CARRIERS,
    CONF_CONFIRMATION_ENABLED,
    CONF_CONFIRMATION_TIME,
    CONF_FOLDER,
    CONF_IMAP_PORT,
    CONF_IMAP_SERVER,
    CONF_IMAP_SSL,
    CONF_IMAP_TIMEOUT,
    CONF_NOTIFY_SERVICE,
    CONF_PASSWORD,
    CONF_PRESET_VERSION,
    CONF_SCAN_INTERVAL,
    CONF_SCAN_WINDOW_DAYS,
    CONF_USERNAME,
    DEFAULT_CONFIRMATION_ENABLED,
    DEFAULT_CONFIRMATION_TIME,
    DEFAULT_FOLDER,
    DEFAULT_IMAP_TIMEOUT,
    DEFAULT_NOTIFY_SERVICE,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_WINDOW_DAYS,
    DOMAIN,
    MAX_IMAP_TIMEOUT,
    MAX_SCAN_INTERVAL,
    MAX_SCAN_WINDOW_DAYS,
    MIN_IMAP_TIMEOUT,
    MIN_SCAN_INTERVAL,
    MIN_SCAN_WINDOW_DAYS,
    PRESET_CARRIERS,
    PRESET_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def _split_lines(value: str) -> list[str]:
    if not value:
        return []
    return [line.strip().lower() for line in value.splitlines() if line.strip()]


def _join_lines(values: list[str]) -> str:
    return "\n".join(values)


def _split_regex_lines(value: str) -> list[str]:
    """Behoud hoofdletters en regex-escapes exact zoals ingevoerd."""
    if not value:
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


def _test_imap_connection(
    server: str,
    port: int,
    use_ssl: bool,
    username: str,
    password: str,
    folder: str,
    timeout: int = DEFAULT_IMAP_TIMEOUT,
) -> None:
    conn = (
        imaplib.IMAP4_SSL(server, port, timeout=timeout)
        if use_ssl
        else imaplib.IMAP4(server, port, timeout=timeout)
    )
    try:
        conn.login(username, password)
        conn.select(folder, readonly=True)
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


class PakketTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Eenmalige setup: IMAP-account koppelen."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(
                    _test_imap_connection,
                    user_input[CONF_IMAP_SERVER],
                    user_input[CONF_IMAP_PORT],
                    user_input[CONF_IMAP_SSL],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_FOLDER],
                )
            except imaplib.IMAP4.error:
                errors["base"] = "invalid_auth"
            except OSError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Onverwachte fout bij IMAP-verbindingstest")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_USERNAME]}_{user_input[CONF_IMAP_SERVER]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Pakket Tracker ({user_input[CONF_USERNAME]})",
                    data=user_input,
                    options={
                        CONF_CARRIERS: deepcopy(PRESET_CARRIERS),
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_IMAP_TIMEOUT: DEFAULT_IMAP_TIMEOUT,
                        CONF_SCAN_WINDOW_DAYS: DEFAULT_SCAN_WINDOW_DAYS,
                        CONF_CONFIRMATION_ENABLED: DEFAULT_CONFIRMATION_ENABLED,
                        CONF_CONFIRMATION_TIME: DEFAULT_CONFIRMATION_TIME,
                        CONF_NOTIFY_SERVICE: DEFAULT_NOTIFY_SERVICE,
                        CONF_PRESET_VERSION: PRESET_VERSION,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_IMAP_SERVER, default="imap.gmail.com"): str,
                vol.Required(CONF_IMAP_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_IMAP_SSL, default=True): bool,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_FOLDER, default=DEFAULT_FOLDER): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Start herauthenticatie na een afgewezen IMAP-wachtwoord."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Vraag alleen een nieuw wachtwoord en test dit vóór opslag."""
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(
                    _test_imap_connection,
                    entry.data[CONF_IMAP_SERVER],
                    entry.data[CONF_IMAP_PORT],
                    entry.data[CONF_IMAP_SSL],
                    entry.data[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    entry.data.get(CONF_FOLDER, DEFAULT_FOLDER),
                    entry.options.get(CONF_IMAP_TIMEOUT, DEFAULT_IMAP_TIMEOUT),
                )
            except imaplib.IMAP4.error:
                errors["base"] = "invalid_auth"
            except OSError:
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> PakketTrackerOptionsFlow:
        return PakketTrackerOptionsFlow()


class PakketTrackerOptionsFlow(config_entries.OptionsFlow):
    """Vervoerders beheren: toevoegen, bewerken, verwijderen."""

    def __init__(self) -> None:
        self._carriers: dict[str, dict] = {}
        self._options_loaded = False
        self._selected_carrier_id: str | None = None

    def _ensure_options_loaded(self) -> None:
        """Kopieer opties nadat Home Assistant de config-entry heeft gekoppeld."""
        if self._options_loaded:
            return
        self._carriers = deepcopy(
            dict(self.config_entry.options.get(CONF_CARRIERS, {}))
        )
        self._options_loaded = True

    def _save(self) -> FlowResult:
        self._ensure_options_loaded()
        return self.async_create_entry(
            title="",
            data={
                CONF_CARRIERS: self._carriers,
                CONF_SCAN_INTERVAL: self.config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                ),
                CONF_IMAP_TIMEOUT: self.config_entry.options.get(
                    CONF_IMAP_TIMEOUT, DEFAULT_IMAP_TIMEOUT
                ),
                CONF_SCAN_WINDOW_DAYS: self.config_entry.options.get(
                    CONF_SCAN_WINDOW_DAYS, DEFAULT_SCAN_WINDOW_DAYS
                ),
                CONF_CONFIRMATION_ENABLED: self.config_entry.options.get(
                    CONF_CONFIRMATION_ENABLED, DEFAULT_CONFIRMATION_ENABLED
                ),
                CONF_CONFIRMATION_TIME: self.config_entry.options.get(
                    CONF_CONFIRMATION_TIME, DEFAULT_CONFIRMATION_TIME
                ),
                CONF_NOTIFY_SERVICE: self.config_entry.options.get(
                    CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE
                ),
                CONF_PRESET_VERSION: self.config_entry.options.get(
                    CONF_PRESET_VERSION, PRESET_VERSION
                ),
            },
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        self._ensure_options_loaded()
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_simple_carrier",
                "add_carrier",
                "edit_carrier",
                "remove_carrier",
                "scan_interval",
                "finish",
            ],
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return self._save()

    async def async_step_scan_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        self._ensure_options_loaded()
        errors: dict[str, str] = {}
        if user_input is not None:
            confirmation_time = user_input[CONF_CONFIRMATION_TIME].strip()
            notify_service = user_input.get(CONF_NOTIFY_SERVICE, "").strip()
            if (
                re.fullmatch(
                    r"(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?",
                    confirmation_time,
                )
                is None
            ):
                errors[CONF_CONFIRMATION_TIME] = "invalid_confirmation_time"
            elif (
                notify_service
                and re.fullmatch(r"notify\.[a-z0-9_]+", notify_service) is None
            ):
                errors[CONF_NOTIFY_SERVICE] = "invalid_notify_service"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_CARRIERS: self._carriers,
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                        CONF_IMAP_TIMEOUT: user_input[CONF_IMAP_TIMEOUT],
                        CONF_SCAN_WINDOW_DAYS: user_input[CONF_SCAN_WINDOW_DAYS],
                        CONF_CONFIRMATION_ENABLED: user_input[
                            CONF_CONFIRMATION_ENABLED
                        ],
                        CONF_CONFIRMATION_TIME: confirmation_time,
                        CONF_NOTIFY_SERVICE: notify_service,
                        CONF_PRESET_VERSION: self.config_entry.options.get(
                            CONF_PRESET_VERSION, PRESET_VERSION
                        ),
                    },
                )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=(user_input or self.config_entry.options).get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
                vol.Required(
                    CONF_IMAP_TIMEOUT,
                    default=(user_input or self.config_entry.options).get(
                        CONF_IMAP_TIMEOUT, DEFAULT_IMAP_TIMEOUT
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_IMAP_TIMEOUT, max=MAX_IMAP_TIMEOUT),
                ),
                vol.Required(
                    CONF_SCAN_WINDOW_DAYS,
                    default=(user_input or self.config_entry.options).get(
                        CONF_SCAN_WINDOW_DAYS, DEFAULT_SCAN_WINDOW_DAYS
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_WINDOW_DAYS, max=MAX_SCAN_WINDOW_DAYS),
                ),
                vol.Required(
                    CONF_CONFIRMATION_ENABLED,
                    default=(user_input or self.config_entry.options).get(
                        CONF_CONFIRMATION_ENABLED, DEFAULT_CONFIRMATION_ENABLED
                    ),
                ): bool,
                vol.Required(
                    CONF_CONFIRMATION_TIME,
                    default=(user_input or self.config_entry.options).get(
                        CONF_CONFIRMATION_TIME, DEFAULT_CONFIRMATION_TIME
                    ),
                ): str,
                vol.Optional(
                    CONF_NOTIFY_SERVICE,
                    default=(user_input or self.config_entry.options).get(
                        CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE
                    ),
                ): str,
            }
        )
        return self.async_show_form(
            step_id="scan_interval", data_schema=schema, errors=errors
        )

    async def async_step_add_simple_carrier(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Voeg een vervoerder toe met één gecontroleerde titel per status."""
        self._ensure_options_loaded()
        errors: dict[str, str] = {}
        if user_input is not None:
            carrier_name = user_input[CARRIER_NAME].strip()
            email_address = user_input["email_address"].strip().lower()
            delivering_title = user_input["delivering_title"].strip().lower()
            carrier_id = carrier_name.strip().lower().replace(" ", "_").replace(".", "")
            if not carrier_id:
                errors["base"] = "invalid_name"
            elif re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email_address) is None:
                errors["email_address"] = "invalid_email_address"
            elif not delivering_title:
                errors["delivering_title"] = "required_status_text"
            elif carrier_id in self._carriers:
                errors["base"] = "already_exists"
            else:
                self._carriers[carrier_id] = {
                    CARRIER_NAME: carrier_name,
                    CARRIER_SENDERS: [email_address],
                    CARRIER_REGISTERED_SUBJECTS: (
                        [user_input["registered_title"].strip().lower()]
                        if user_input.get("registered_title", "").strip()
                        else []
                    ),
                    CARRIER_TRANSIT_SUBJECTS: (
                        [user_input["transit_title"].strip().lower()]
                        if user_input.get("transit_title", "").strip()
                        else []
                    ),
                    CARRIER_DELIVERING_SUBJECTS: [delivering_title],
                    CARRIER_DELIVERED_SUBJECTS: (
                        [user_input["delivered_title"].strip().lower()]
                        if user_input.get("delivered_title", "").strip()
                        else []
                    ),
                    CARRIER_MISSED_SUBJECTS: (
                        [user_input["missed_title"].strip().lower()]
                        if user_input.get("missed_title", "").strip()
                        else []
                    ),
                    CARRIER_TRACKING_PATTERNS: [],
                }
                return self._save()

        schema = vol.Schema(
            {
                vol.Required(CARRIER_NAME): str,
                vol.Required("email_address"): str,
                vol.Optional("registered_title", default=""): str,
                vol.Optional("transit_title", default=""): str,
                vol.Required("delivering_title"): str,
                vol.Optional("delivered_title", default=""): str,
                vol.Optional("missed_title", default=""): str,
            }
        )
        return self.async_show_form(
            step_id="add_simple_carrier", data_schema=schema, errors=errors
        )

    async def async_step_add_carrier(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            carrier_id = (
                user_input[CARRIER_NAME]
                .strip()
                .lower()
                .replace(" ", "_")
                .replace(".", "")
            )
            if not carrier_id:
                errors["base"] = "invalid_name"
            elif carrier_id in self._carriers:
                errors["base"] = "already_exists"
            else:
                self._carriers[carrier_id] = {
                    CARRIER_NAME: user_input[CARRIER_NAME].strip(),
                    CARRIER_SENDERS: _split_lines(user_input[CARRIER_SENDERS]),
                    CARRIER_REGISTERED_SUBJECTS: _split_lines(
                        user_input.get(CARRIER_REGISTERED_SUBJECTS, "")
                    ),
                    CARRIER_TRANSIT_SUBJECTS: _split_lines(
                        user_input.get(CARRIER_TRANSIT_SUBJECTS, "")
                    ),
                    CARRIER_DELIVERING_SUBJECTS: _split_lines(
                        user_input[CARRIER_DELIVERING_SUBJECTS]
                    ),
                    CARRIER_DELIVERED_SUBJECTS: _split_lines(
                        user_input.get(CARRIER_DELIVERED_SUBJECTS, "")
                    ),
                    CARRIER_MISSED_SUBJECTS: _split_lines(
                        user_input.get(CARRIER_MISSED_SUBJECTS, "")
                    ),
                    CARRIER_TRACKING_PATTERNS: _split_regex_lines(
                        user_input.get(CARRIER_TRACKING_PATTERNS, "")
                    ),
                }
                return self._save()

        schema = vol.Schema(
            {
                vol.Required(CARRIER_NAME): str,
                vol.Required(CARRIER_SENDERS): str,
                vol.Optional(CARRIER_REGISTERED_SUBJECTS, default=""): str,
                vol.Optional(CARRIER_TRANSIT_SUBJECTS, default=""): str,
                vol.Required(CARRIER_DELIVERING_SUBJECTS): str,
                vol.Optional(CARRIER_DELIVERED_SUBJECTS, default=""): str,
                vol.Optional(CARRIER_MISSED_SUBJECTS, default=""): str,
                vol.Optional(CARRIER_TRACKING_PATTERNS, default=""): str,
            }
        )
        return self.async_show_form(
            step_id="add_carrier", data_schema=schema, errors=errors
        )

    async def async_step_edit_carrier(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not self._carriers:
            return self.async_abort(reason="no_carriers")
        if user_input is not None:
            self._selected_carrier_id = user_input["carrier_id"]
            return await self.async_step_edit_carrier_form()

        schema = vol.Schema(
            {
                vol.Required("carrier_id"): vol.In(
                    {cid: c[CARRIER_NAME] for cid, c in self._carriers.items()}
                )
            }
        )
        return self.async_show_form(step_id="edit_carrier", data_schema=schema)

    async def async_step_edit_carrier_form(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        carrier_id = self._selected_carrier_id
        carrier = self._carriers[carrier_id]

        if user_input is not None:
            carrier[CARRIER_SENDERS] = _split_lines(user_input[CARRIER_SENDERS])
            carrier[CARRIER_REGISTERED_SUBJECTS] = _split_lines(
                user_input.get(CARRIER_REGISTERED_SUBJECTS, "")
            )
            carrier[CARRIER_TRANSIT_SUBJECTS] = _split_lines(
                user_input.get(CARRIER_TRANSIT_SUBJECTS, "")
            )
            carrier[CARRIER_DELIVERING_SUBJECTS] = _split_lines(
                user_input[CARRIER_DELIVERING_SUBJECTS]
            )
            carrier[CARRIER_DELIVERED_SUBJECTS] = _split_lines(
                user_input.get(CARRIER_DELIVERED_SUBJECTS, "")
            )
            carrier[CARRIER_MISSED_SUBJECTS] = _split_lines(
                user_input.get(CARRIER_MISSED_SUBJECTS, "")
            )
            carrier[CARRIER_TRACKING_PATTERNS] = _split_regex_lines(
                user_input.get(CARRIER_TRACKING_PATTERNS, "")
            )
            self._carriers[carrier_id] = carrier
            return self._save()

        schema = vol.Schema(
            {
                vol.Required(
                    CARRIER_SENDERS, default=_join_lines(carrier[CARRIER_SENDERS])
                ): str,
                vol.Optional(
                    CARRIER_REGISTERED_SUBJECTS,
                    default=_join_lines(carrier.get(CARRIER_REGISTERED_SUBJECTS, [])),
                ): str,
                vol.Optional(
                    CARRIER_TRANSIT_SUBJECTS,
                    default=_join_lines(carrier.get(CARRIER_TRANSIT_SUBJECTS, [])),
                ): str,
                vol.Required(
                    CARRIER_DELIVERING_SUBJECTS,
                    default=_join_lines(carrier[CARRIER_DELIVERING_SUBJECTS]),
                ): str,
                vol.Optional(
                    CARRIER_DELIVERED_SUBJECTS,
                    default=_join_lines(carrier[CARRIER_DELIVERED_SUBJECTS]),
                ): str,
                vol.Optional(
                    CARRIER_MISSED_SUBJECTS,
                    default=_join_lines(carrier.get(CARRIER_MISSED_SUBJECTS, [])),
                ): str,
                vol.Optional(
                    CARRIER_TRACKING_PATTERNS,
                    default=_join_lines(carrier.get(CARRIER_TRACKING_PATTERNS, [])),
                ): str,
            }
        )
        return self.async_show_form(
            step_id="edit_carrier_form",
            data_schema=schema,
            description_placeholders={"carrier_name": carrier[CARRIER_NAME]},
        )

    async def async_step_remove_carrier(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not self._carriers:
            return self.async_abort(reason="no_carriers")
        if user_input is not None:
            self._carriers.pop(user_input["carrier_id"], None)
            return self._save()

        schema = vol.Schema(
            {
                vol.Required("carrier_id"): vol.In(
                    {cid: c[CARRIER_NAME] for cid, c in self._carriers.items()}
                )
            }
        )
        return self.async_show_form(step_id="remove_carrier", data_schema=schema)
