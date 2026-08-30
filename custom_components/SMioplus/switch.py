"""Relays on the card."""

DEFAULT_ICONS = {
        "on": "mdi:toggle-switch-variant",
        "off": "mdi:toggle-switch-variant-off",
}

from homeassistant.components.switch import SwitchEntity

from .data import SM_MAP
from .entity import SMWritableEntity, async_setup_sm_platform

PLATFORM = "switch"
SM_MAP = SM_MAP.get(PLATFORM, {})


async def async_setup_platform(hass, config, add_devices, discovery_info=None):
    await async_setup_sm_platform(
        hass, PLATFORM, discovery_info, add_devices,
        lambda channel, name, coordinator: Switch(channel, name, coordinator),
    )


class Switch(SMWritableEntity, SwitchEntity):
    def __init__(self, channel, name, coordinator):
        super().__init__(channel, name, coordinator, DEFAULT_ICONS)
        ### __CUSTOM_SETUP__ START
        ### __CUSTOM_SETUP__ END

    @property
    def is_on(self):
        if self._sm_value is None:
            return None
        return bool(self._sm_value)

    async def async_turn_on(self, **kwargs):
        await self._sm_set(1)

    async def async_turn_off(self, **kwargs):
        await self._sm_set(0)

    async def _sm_set(self, value):
        await self._sm_write(value)
        # Show the new position straight away; the next sweep confirms it
        # against the card.
        self._sm_ingest(value)
        self.async_write_ha_state()
