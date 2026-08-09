"""Config flow for Solakon Cloud."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    SolakonApiClient,
    SolakonAuthError,
    SolakonConnectionError,
    SolakonOtpError,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)


class SolakonCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Solakon Cloud OTP setup flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._email: str | None = None
        self._client: SolakonApiClient | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect email and request an OTP."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = user_input[CONF_EMAIL].strip().lower()
            await self.async_set_unique_id(self._email)
            self._abort_if_unique_id_configured()
            error = await self._async_send_otp()
            if error is None:
                return await self.async_step_otp()
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_EMAIL): str}),
            errors=errors,
        )

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Verify the six-digit email code."""
        if self._email is None or self._client is None:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}
        if user_input is not None:
            code = str(user_input["code"]).strip()
            if not re.fullmatch(r"\d{6}", code):
                errors["code"] = "invalid_otp"
            else:
                try:
                    tokens = await self._client.async_verify_otp(self._email, code)
                    devices = await self._client.async_get_inverters()
                    if not devices:
                        errors["base"] = "no_devices"
                    else:
                        data = {
                            CONF_EMAIL: self._email,
                            CONF_ACCESS_TOKEN: tokens.access_token,
                            CONF_REFRESH_TOKEN: tokens.refresh_token,
                            CONF_EXPIRES_AT: tokens.expires_at,
                        }
                        if self._reauth_entry is not None:
                            self.hass.config_entries.async_update_entry(
                                self._reauth_entry, data=data
                            )
                            await self.hass.config_entries.async_reload(
                                self._reauth_entry.entry_id
                            )
                            return self.async_abort(reason="reauth_successful")
                        return self.async_create_entry(
                            title=f"Solakon Cloud ({self._email})", data=data
                        )
                except SolakonOtpError:
                    errors["code"] = "invalid_otp"
                except SolakonConnectionError:
                    errors["base"] = "cannot_connect"
                except SolakonAuthError:
                    errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="otp",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
            description_placeholders={"email": self._email},
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Start reauthentication for an expired refresh token."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self._email = entry_data[CONF_EMAIL]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm before sending a new email."""
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_send_otp()
            if error is None:
                return await self.async_step_otp()
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"email": self._email or ""},
        )

    async def _async_send_otp(self) -> str | None:
        """Create a client and request the confirmation email."""
        assert self._email is not None
        self._client = SolakonApiClient(async_get_clientsession(self.hass))
        try:
            await self._client.async_request_otp(self._email)
        except SolakonConnectionError:
            return "cannot_connect"
        except SolakonOtpError:
            return "invalid_auth"
        return None
