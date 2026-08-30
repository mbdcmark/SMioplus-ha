"""Reset buttons on the card."""

DEFAULT_ICONS = {
        "off": "mdi:button-pointer",
}

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .data import SM_MAP
from .entity import SMEntityMixin, async_setup_sm_platform

PLATFORM = "button"
SM_MAP = SM_MAP[PLATFORM]

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, add_devices, discovery_info=None):
    await async_setup_sm_platform(
        hass, PLATFORM, discovery_info, add_devices,
        lambda channel, name: Button(channel, name),
        polled=False,
    )


class Button(SMEntityMixin, ButtonEntity):
    """A button has nothing to read back, so it is not part of any sweep."""

    _attr_should_poll = False

    def __init__(self, channel, name):
        self._sm_setup(channel, name, DEFAULT_ICONS)
        ### __CUSTOM_SETUP__ START
        ### __CUSTOM_SETUP__ END

    async def async_press(self):
        try:
            await self.hass.async_add_executor_job(self._sm_channel.set)
        except Exception as ex:  # noqa: BLE001 - the vendor library raises bare
            # OSError/IOError on bus trouble.
            _LOGGER.error("Pressing %s failed: %s", self._sm_channel, ex)
            raise HomeAssistantError(
                f"Pressing {self._sm_channel} failed: {ex}"
            ) from ex
