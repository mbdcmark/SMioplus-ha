"""On/off inputs on the card."""

DEFAULT_ICONS = {
        "on": "mdi:numeric-1",
        "off": "mdi:numeric-0",
}

from homeassistant.components.binary_sensor import BinarySensorEntity

from .data import SM_MAP
from .entity import SMPolledEntity, async_setup_sm_platform

PLATFORM = "binary_sensor"
SM_MAP = SM_MAP[PLATFORM]


async def async_setup_platform(hass, config, add_devices, discovery_info=None):
    await async_setup_sm_platform(
        hass, PLATFORM, discovery_info, add_devices,
        lambda channel, name, coordinator: BinarySensor(channel, name, coordinator),
    )


class BinarySensor(SMPolledEntity):
    def __init__(self, channel, name, coordinator):
        super().__init__(channel, name, coordinator, DEFAULT_ICONS)
        self._attr_device_class = SM_MAP[channel.entity_type].get("device_class")
        ### __CUSTOM_SETUP__ START
        ### __CUSTOM_SETUP__ END

    @property
    def is_on(self):
        if self._sm_value is None:
            return None
        return bool(self._sm_value)
