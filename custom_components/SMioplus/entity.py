"""Shared behaviour for every SMioplus entity.

This replaces the four near-identical copies of the setup and API binding code
that used to live in button.py, sensor.py, switch.py and number.py.
"""

import logging
import time

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SMChannel
from .const import (
    CONF_CHAN,
    CONF_NAME,
    CONF_STACK,
    CONF_TYPE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
)
from .coordinator import async_get_coordinator
from .data import DOMAIN, NAME_PREFIX, NAME_STACK_OFFSET, SM_MAP

_LOGGER = logging.getLogger(__name__)


async def async_setup_sm_platform(
    hass, platform, discovery_info, add_entities, factory, polled=True
):
    """Turn one discovery message into one entity.

    ``factory`` is called with (channel, name, coordinator) for polled
    platforms and (channel, name) for platforms that only write.
    """
    # We want this platform to be set up via discovery.
    if discovery_info is None:
        return

    stack = int(discovery_info[CONF_STACK])
    entity_type = discovery_info[CONF_TYPE]
    chan = int(discovery_info[CONF_CHAN])
    name = discovery_info.get(CONF_NAME)

    # Binding touches the bus (and may construct the vendor class), so it must
    # not run on the event loop.
    try:
        channel = await hass.async_add_executor_job(
            SMChannel, platform, entity_type, stack, chan
        )
    except Exception as err:  # noqa: BLE001 - SMApiError when the card
        # description and the library disagree, OSError when the card is not
        # on the bus.  Either way, skip this entity instead of failing the
        # whole platform.
        _LOGGER.error("Skipping %s_%s on stack %s: %s", entity_type, chan, stack, err)
        return

    if not polled:
        add_entities([factory(channel, name)])
        return

    # configuration.yaml wins; then whatever the card description asks for
    # this entity type; then the integration default.
    spec = SM_MAP[platform][entity_type]
    interval = float(
        discovery_info.get(CONF_UPDATE_INTERVAL)
        or spec.get(CONF_UPDATE_INTERVAL)
        or DEFAULT_UPDATE_INTERVAL
    )
    coordinator = async_get_coordinator(hass, stack, interval)
    coordinator.register(channel)
    add_entities([factory(channel, name, coordinator)])


class SMEntityMixin:
    """Identity, naming and device grouping, shared by all platforms."""

    _attr_has_entity_name = False

    def _sm_setup(self, channel, name, default_icons):
        spec = SM_MAP[channel.platform][channel.entity_type]
        self._sm_channel = channel

        # Deterministic, so it survives a restart unchanged.  This used to be
        # derived from generate_entity_id(), which consults the state machine
        # and appends _2 on what it thinks is a collision -- registering the
        # same entity twice after a reload.
        self._attr_unique_id = (
            f"{DOMAIN}_{channel.stack}_{channel.entity_type}_{channel.chan}"
        )
        self._attr_name = name or (
            f"{NAME_PREFIX}{channel.stack + NAME_STACK_OFFSET}"
            f"_{channel.entity_type}_{channel.chan}"
        )
        # No device_info on purpose.  Home Assistant only lets an entity join
        # the device registry through a config entry, and this integration is
        # configured from YAML, so grouping the channels of a card under one
        # device earned a deprecation warning on every start and would have
        # stopped working in 2027.8.  It comes back with a config flow, not
        # before.

        self._sm_icons = {**default_icons, **spec.get("icon", {})}
        self._attr_icon = self._sm_icons.get("off")

    def _sm_apply_icon(self, value):
        state = "on" if value else "off"
        self._attr_icon = self._sm_icons.get(state) or self._sm_icons.get("off")


class SMPolledEntity(SMEntityMixin, CoordinatorEntity):
    """An entity whose value comes from the card's coordinator sweep."""

    # Set when this entity last drove the card, so a sweep that read the card
    # before that can be told apart from one that read it after.
    _sm_written_at = 0.0

    def __init__(self, channel, name, coordinator, default_icons):
        CoordinatorEntity.__init__(self, coordinator, context=channel.key)
        self._sm_setup(channel, name, default_icons)
        self._sm_value = None

    @property
    def available(self):
        return super().available and self._sm_value is not None

    def _sm_ingest(self, value):
        """Take a freshly read value. Subclasses map it onto their state."""
        self._sm_value = value
        self._sm_apply_icon(value)

    def _handle_coordinator_update(self):
        if self.coordinator.sweep_started < self._sm_written_at:
            # This sweep read the card before our write reached it, so its
            # answer is stale.  Switching eight relays at once used to land
            # some of them back on for a whole interval this way.
            return
        # data is still None when the very first sweep failed.
        data = self.coordinator.data or {}
        self._sm_ingest(data.get(self._sm_channel.key))
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.coordinator.data is not None:
            self._sm_ingest(self.coordinator.data.get(self._sm_channel.key))
        # The coordinator's timer does not fire until a full interval has
        # passed.  Requests from all entities are debounced into one sweep.
        await self.coordinator.async_request_refresh()


class SMWritableEntity(SMPolledEntity):
    """A polled entity that also drives the card."""

    async def _sm_write(self, *values):
        try:
            await self.hass.async_add_executor_job(self._sm_channel.set, *values)
        except Exception as ex:  # noqa: BLE001 - the vendor library raises bare
            # OSError/IOError on bus trouble.
            _LOGGER.error("Writing %s failed: %s", self._sm_channel, ex)
            raise HomeAssistantError(f"Writing {self._sm_channel} failed: {ex}") from ex
        # Any sweep already under way read the card before this, so mark the
        # moment before asking for a fresh one.
        self._sm_written_at = time.monotonic()
        await self.coordinator.async_request_refresh()
