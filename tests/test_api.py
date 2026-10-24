"""Regression tests for the Solakon API client."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
from types import ModuleType
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock


# Import the API module without executing the integration package's
# Home Assistant-dependent __init__.py.
PACKAGE = "custom_components.solakon_cloud"
package = ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).parents[1] / "custom_components" / "solakon_cloud")
]
sys.modules.setdefault(PACKAGE, package)
api = importlib.import_module(f"{PACKAGE}.api")


class TestOptionalControlEndpoints(IsolatedAsyncioTestCase):
    """Ensure optional controls cannot block otherwise valid telemetry."""

    async def test_maximum_power_ignores_temporary_server_error(self) -> None:
        client = api.SolakonApiClient(object())
        client.async_get = AsyncMock(
            side_effect=api.SolakonApiError("Internal server error", 500)
        )

        self.assertIsNone(await client.async_get_maximum_power("device"))

    async def test_mode_ignores_temporary_server_error(self) -> None:
        client = api.SolakonApiClient(object())
        client.async_get = AsyncMock(
            side_effect=api.SolakonApiError("Service unavailable", 503)
        )

        self.assertIsNone(await client.async_get_mode("device"))

    async def test_unexpected_error_is_not_hidden(self) -> None:
        client = api.SolakonApiClient(object())
        client.async_get = AsyncMock(
            side_effect=api.SolakonApiError("Too many requests", 429)
        )

        with self.assertRaises(api.SolakonApiError):
            await client.async_get_maximum_power("device")
