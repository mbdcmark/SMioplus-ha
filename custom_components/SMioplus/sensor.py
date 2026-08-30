"""Numeric readings from the card."""

DEFAULT_ICONS = {
        "on": "mdi:numeric",
        "off": "mdi:numeric-0",
}

from homeassistant.components.sensor import SensorEntity

from .data import SM_MAP
from .entity import SMPolledEntity, async_setup_sm_platform

PLATFORM = "sensor"
SM_MAP = SM_MAP[PLATFORM]


async def async_setup_platform(hass, config, add_devices, discovery_info=None):
    await async_setup_sm_platform(
        hass, PLATFORM, discovery_info, add_devices,
        lambda channel, name, coordinator: Sensor(channel, name, coordinator),
    )


class Sensor(SMPolledEntity, SensorEntity):
    def __init__(self, channel, name, coordinator):
        super().__init__(channel, name, coordinator, DEFAULT_ICONS)
        spec = SM_MAP[channel.entity_type]
        self._attr_native_unit_of_measurement = spec.get("uom") or None
        self._attr_device_class = spec.get("device_class")
        self._attr_state_class = spec.get("state_class")
        ### __CUSTOM_SETUP__ START
        ### __CUSTOM_SETUP__ END

    @property
    def native_value(self):
        # None until the first sweep lands, so the entity reads "unknown"
        # instead of claiming a value of 0 it never measured.
        return self._sm_value
