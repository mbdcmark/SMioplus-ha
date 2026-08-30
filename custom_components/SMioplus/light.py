"""Analog outputs as dimmers.

The open drain channels are PWM and the DAC channels are 0-10V, which is what
a 0-10V dimmer expects, so both are lights with a brightness. Switching one off
writes zero to the hardware but remembers the level, and switching it back on
returns to it -- across a restart as well.
"""

DEFAULT_ICONS = {
        "on": "mdi:lightbulb",
        "off": "mdi:lightbulb-off",
}

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .data import SM_MAP
from .entity import SMWritableEntity, async_setup_sm_platform

PLATFORM = "light"
SM_MAP = SM_MAP.get(PLATFORM, {})

# Home Assistant counts brightness in 1..255; the card counts volts or percent.
MAX_BRIGHTNESS = 255

# Remembered level, kept as an attribute so it survives a restart even when the
# light was off at the time and Home Assistant recorded no brightness.
ATTR_LEVEL_WHEN_ON = "brightness_when_on"


async def async_setup_platform(hass, config, add_devices, discovery_info=None):
    await async_setup_sm_platform(
        hass, PLATFORM, discovery_info, add_devices,
        lambda channel, name, coordinator: Light(channel, name, coordinator),
    )


class Light(SMWritableEntity, LightEntity, RestoreEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, channel, name, coordinator):
        super().__init__(channel, name, coordinator, DEFAULT_ICONS)
        spec = SM_MAP[channel.entity_type]
        self._sm_off = float(spec["min_value"])
        self._sm_full = float(spec["max_value"])
        self._sm_level = None
        ### __CUSTOM_SETUP__ START
        ### __CUSTOM_SETUP__ END

    def _to_brightness(self, value):
        span = self._sm_full - self._sm_off
        share = (float(value) - self._sm_off) / span if span else 0.0
        share = min(max(share, 0.0), 1.0)
        if share <= 0:
            return 0
        # 0.01V of a 10V range rounds to nothing, and a light that is on must
        # not report a brightness of zero.
        return max(1, round(share * MAX_BRIGHTNESS))

    def _to_native(self, brightness):
        span = self._sm_full - self._sm_off
        share = min(max(brightness, 0), MAX_BRIGHTNESS) / MAX_BRIGHTNESS
        return self._sm_off + share * span

    def _sm_ingest(self, value):
        super()._sm_ingest(value)
        # Anything above off is the level to come back to.
        if value is not None and float(value) > self._sm_off:
            self._sm_level = float(value)

    @property
    def is_on(self):
        if self._sm_value is None:
            return None
        return float(self._sm_value) > self._sm_off

    @property
    def brightness(self):
        if self._sm_value is None:
            return None
        return self._to_brightness(self._sm_value)

    @property
    def extra_state_attributes(self):
        if self._sm_level is None:
            return None
        return {ATTR_LEVEL_WHEN_ON: self._to_brightness(self._sm_level)}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None:
            return
        remembered = last.attributes.get(ATTR_LEVEL_WHEN_ON) or last.attributes.get(
            ATTR_BRIGHTNESS
        )
        if remembered and self._sm_level is None:
            self._sm_level = self._to_native(remembered)

    async def async_turn_on(self, **kwargs):
        if ATTR_BRIGHTNESS in kwargs:
            native = self._to_native(kwargs[ATTR_BRIGHTNESS])
        else:
            # Back to where it was, or all the way up if it has never been on.
            native = self._sm_level if self._sm_level is not None else self._sm_full
        await self._sm_apply(native)

    async def async_turn_off(self, **kwargs):
        await self._sm_apply(self._sm_off)

    async def _sm_apply(self, native):
        await self._sm_write(native)
        # Show it straight away; the next sweep confirms it against the card.
        self._sm_ingest(native)
        self.async_write_ha_state()
