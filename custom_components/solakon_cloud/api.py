"""Small asynchronous client for the Solakon app API.

This API is used by Solakon's own web application but is not a published public
API. Keep all protocol-specific behavior in this module so it can be adjusted
without touching the Home Assistant entities.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import time
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession

from .const import (
    API_BASE_URL,
    APP_VERSION,
    AUTH_BASE_URL,
    REQUEST_TIMEOUT,
    SUPABASE_ANON_KEY,
)


class SolakonError(Exception):
    """Base Solakon exception."""


class SolakonConnectionError(SolakonError):
    """Raised when the cloud cannot be reached."""


class SolakonAuthError(SolakonError):
    """Raised when authentication is no longer valid."""


class SolakonOtpError(SolakonAuthError):
    """Raised when an OTP cannot be requested or verified."""


class SolakonApiError(SolakonError):
    """Raised for an unexpected API response."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(slots=True)
class SolakonTokens:
    """Renewable Solakon session."""

    access_token: str
    refresh_token: str
    expires_at: float


TokenCallback = Callable[[SolakonTokens], Awaitable[None]]


def _message(payload: Any, fallback: str) -> str:
    """Extract a safe error message from a Supabase/API response."""
    if isinstance(payload, dict):
        for key in ("message", "msg", "error_description", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return fallback


async def _json_or_text(response: ClientResponse) -> Any:
    """Return JSON when possible, otherwise the response text."""
    try:
        return await response.json(content_type=None)
    except (ValueError, ClientError):
        return await response.text()


class SolakonApiClient:
    """Client implementing Solakon OTP, token refresh, reads and controls."""

    def __init__(
        self,
        session: ClientSession,
        tokens: SolakonTokens | None = None,
        token_callback: TokenCallback | None = None,
    ) -> None:
        self._session = session
        self._tokens = tokens
        self._token_callback = token_callback
        self._refresh_lock = asyncio.Lock()

    @property
    def tokens(self) -> SolakonTokens | None:
        """Return the active tokens."""
        return self._tokens

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        return {
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
            "Content-Type": "application/json",
        }

    async def async_request_otp(self, email: str) -> None:
        """Send a six-digit code without creating an account for typos."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.post(
                    f"{AUTH_BASE_URL}/otp",
                    headers=self._auth_headers(),
                    json={"email": email, "create_user": False, "data": {}},
                )
                payload = await _json_or_text(response)
        except (TimeoutError, ClientError) as err:
            raise SolakonConnectionError("Unable to reach Solakon authentication") from err

        if response.status >= 400:
            raise SolakonOtpError(_message(payload, "Unable to send confirmation code"))

    async def async_verify_otp(self, email: str, code: str) -> SolakonTokens:
        """Exchange the emailed code for a renewable session."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.post(
                    f"{AUTH_BASE_URL}/verify",
                    headers=self._auth_headers(),
                    json={"email": email, "token": code, "type": "email"},
                )
                payload = await _json_or_text(response)
        except (TimeoutError, ClientError) as err:
            raise SolakonConnectionError("Unable to reach Solakon authentication") from err

        if response.status >= 400 or not isinstance(payload, dict):
            raise SolakonOtpError(_message(payload, "Invalid confirmation code"))

        tokens = self._tokens_from_payload(payload)
        await self._set_tokens(tokens)
        return tokens

    @staticmethod
    def _tokens_from_payload(payload: dict[str, Any]) -> SolakonTokens:
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            raise SolakonAuthError("Solakon did not return a renewable session")

        expires_at = payload.get("expires_at")
        if not isinstance(expires_at, (int, float)):
            expires_in = payload.get("expires_in", 3600)
            expires_at = time.time() + float(expires_in)
        return SolakonTokens(access_token, refresh_token, float(expires_at))

    async def _set_tokens(self, tokens: SolakonTokens) -> None:
        self._tokens = tokens
        if self._token_callback is not None:
            await self._token_callback(tokens)

    async def async_refresh_tokens(self, force: bool = False) -> None:
        """Refresh the session, serializing concurrent refresh attempts."""
        async with self._refresh_lock:
            if self._tokens is None:
                raise SolakonAuthError("No Solakon session is configured")
            if not force and self._tokens.expires_at > time.time() + 90:
                return

            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    response = await self._session.post(
                        f"{AUTH_BASE_URL}/token?grant_type=refresh_token",
                        headers=self._auth_headers(),
                        json={"refresh_token": self._tokens.refresh_token},
                    )
                    payload = await _json_or_text(response)
            except (TimeoutError, ClientError) as err:
                raise SolakonConnectionError("Unable to refresh Solakon session") from err

            if response.status >= 400 or not isinstance(payload, dict):
                raise SolakonAuthError(_message(payload, "Solakon session expired"))
            await self._set_tokens(self._tokens_from_payload(payload))

    async def _async_api_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        if self._tokens is None:
            raise SolakonAuthError("No Solakon session is configured")
        await self.async_refresh_tokens()
        assert self._tokens is not None

        headers = {
            # Solakon's own client sends the Supabase JWT without a Bearer prefix.
            "Authorization": self._tokens.access_token,
            "X-App-Version": APP_VERSION,
            "Content-Type": "application/json",
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.request(
                    method,
                    f"{API_BASE_URL}{path}",
                    headers=headers,
                    json=json,
                )
                payload = await _json_or_text(response)
        except (TimeoutError, ClientError) as err:
            raise SolakonConnectionError(f"Unable to reach Solakon API: {path}") from err

        if response.status == 401:
            if retry_auth:
                await self.async_refresh_tokens(force=True)
                return await self._async_api_request(
                    method, path, json=json, retry_auth=False
                )
            raise SolakonAuthError("Solakon rejected the renewed session")
        if response.status >= 400:
            raise SolakonApiError(
                _message(payload, f"Solakon API returned HTTP {response.status}"),
                response.status,
            )
        return payload

    async def async_get(self, path: str) -> Any:
        return await self._async_api_request("GET", path)

    async def async_put(self, path: str, body: dict[str, Any]) -> Any:
        return await self._async_api_request("PUT", path, json=body)

    async def async_get_inverters(self) -> list[dict[str, Any]]:
        """Return account inverters, merging both views used by the app."""
        found: dict[str, dict[str, Any]] = {}

        groups = await self.async_get("/v1/user/groups")
        if isinstance(groups, list):
            for group in groups:
                if not isinstance(group, dict):
                    continue
                candidates: list[Any] = []
                candidates.append(group.get("inverter"))
                if isinstance(group.get("inverters"), list):
                    candidates.extend(group["inverters"])
                for candidate in candidates:
                    self._add_inverter(found, candidate, group)

        # This second endpoint is the source used by the inverter overview. It
        # also covers accounts whose group payload omits shared-device details.
        try:
            inverters = await self.async_get("/v1/user/inverter")
        except SolakonApiError as err:
            if err.status not in (404, 403):
                raise
        else:
            if isinstance(inverters, list):
                for inverter in inverters:
                    self._add_inverter(found, inverter, None)

        return list(found.values())

    @staticmethod
    def _add_inverter(
        found: dict[str, dict[str, Any]],
        candidate: Any,
        group: dict[str, Any] | None,
    ) -> None:
        if not isinstance(candidate, dict):
            return
        device_id = candidate.get("deviceId") or candidate.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            return
        merged = dict(found.get(device_id, {}))
        merged.update(candidate)
        merged["deviceId"] = device_id
        if group is not None:
            merged.setdefault("groupId", group.get("id"))
            merged.setdefault("groupName", group.get("name"))
        found[device_id] = merged

    async def async_get_aggregated(self, device_id: str) -> dict[str, Any]:
        payload = await self.async_get(f"/v1/inverter/{device_id}/aggregated")
        if not isinstance(payload, dict):
            raise SolakonApiError("Unexpected inverter response")
        return payload

    async def async_get_maximum_power(self, device_id: str) -> dict[str, Any] | None:
        try:
            payload = await self.async_get(f"/v1/inverter/{device_id}/maximum-power")
        except SolakonApiError as err:
            if err.status in (400, 403, 404):
                return None
            raise
        return payload if isinstance(payload, dict) else None

    async def async_set_maximum_power(self, device_id: str, power: int) -> Any:
        return await self.async_put(
            f"/v1/inverter/{device_id}/maximum-power", {"power": power}
        )

    async def async_get_mode(self, device_id: str) -> dict[str, Any] | None:
        try:
            payload = await self.async_get(f"/v1/inverter/{device_id}/mode")
        except SolakonApiError as err:
            if err.status in (400, 403, 404):
                return None
            raise
        return payload if isinstance(payload, dict) else None

    async def async_set_mode(self, device_id: str, enabled: bool) -> Any:
        return await self.async_put(
            f"/v1/inverter/{device_id}/mode", {"mode": 1 if enabled else 0}
        )
