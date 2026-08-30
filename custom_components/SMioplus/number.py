"""Analog outputs on the card."""

DEFAULT_ICONS = {
        "on": "mdi:numeric",
        "off": "mdi:numeric-0",
}

from homeassistant.components.number import NumberEntity

from .data import SM_MAP
from .entity import SMWritableEntity, async_setup_sm_platform

PLATFORM = "number"
SM_MAP = SM_MAP.get(PLATFORM, {})


async def async_setup_platform(hass, config, add_devices, discovery_info=None):
    await async_setup_sm_platform(
        hass, PLATFORM, discovery_info, add_devices,
        lambda channel, name, coordinator: (
            Number if channel.readable else NumberNoGet
        )(channel, name, coordinator),
    )


class Number(SMWritableEntity, NumberEntity):
    def __init__(self, channel, name, coordinator):
        super().__init__(channel, name, coordinator, DEFAULT_ICONS)
        spec = SM_MAP[channel.entity_type]
        self._attr_native_unit_of_measurement = spec.get("uom") or None
        self._attr_device_class = spec.get("device_class")
        self._attr_native_min_value = spec["min_value"]
        self._attr_native_max_value = spec["max_value"]
        self._attr_native_step = spec["step"]
        # Some cards want whole numbers.  The range being integral end to end
        # is what says so -- checking only min and step, as this used to, calls
        # a 0..10 range with a 0.5 step integral.
        self._sm_integral = all(
            float(spec[key]) == int(spec[key])
            for key in ("min_value", "max_value", "step")
        )
        ### __CUSTOM_SETUP__ START
        ### __CUSTOM_SETUP__ END

    @property
    def native_value(self):
        return self._sm_value

    async def async_set_native_value(self, value):
        if self._sm_integral:
            value = int(value)
        await self._sm_write(value)
        # Show the new setpoint straight away; the next sweep confirms it
        # against the card.
        self._sm_ingest(value)
        self.async_write_ha_state()


class NumberNoGet(Number):
    """For outputs the card cannot read back: the last written value is the state."""

    def __init__(self, channel, name, coordinator):
        super().__init__(channel, name, coordinator)
        self._sm_value = self._attr_native_min_value

    @property
    def available(self):
        return True

    def _sm_ingest(self, value):
        # Never overwritten by a sweep -- there is nothing to read.
        if value is None:
            return
        self._sm_value = value
        self._sm_apply_icon(value)
