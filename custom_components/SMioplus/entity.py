"""Shared behaviour for every SMioplus entity.

This replaces the near-identical copies of the setup and API binding code that
used to live in each platform module.
"""

import asyncio
import logging
import time

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SMApiError, SMChannel
from .const import (
    BATCH_WINDOW,
    CONF_CHAN,
    CONF_NAME,
    CONF_STACK,
    CONF_TYPE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    WRITE_ATTEMPTS,
    WRITE_SETTLE,
)
from .coordinator import async_get_coordinator
from .data import DOMAIN, NAME_PREFIX, SM_MAP, card_from_stack

_LOGGER = logging.getLogger(__name__)

# One writer per port per card, shared by that port's entities.
_WRITERS = {}


def _port_writer(hass, channel):
    """The batching writer for this channel's port, if it has one."""
    if not channel.batchable:
        return None
    key = (channel.stack, channel.entity_type)
    if key not in _WRITERS:
        _WRITERS[key] = SMPortWriter(hass, channel)
    return _WRITERS[key]


class SMPortWriter:
    """Collects a card's channel writes and sends them as one byte.

    Home Assistant calls turn_on and turn_off one entity at a time, so
    switching eight relays arrived as eight separate transactions and they
    closed in a visible cascade.  Gathering them over a short window turns
    that into a single write, and the relays switch together.
    """

    def __init__(self, hass, channel):
        self.hass = hass
        self._channel = channel
        self._pending = {}
        self._flush = None
        self._gate = asyncio.Lock()

    async def set(self, chan, value):
        """Ask for one channel, and wait for the write that carries it."""
        async with self._gate:
            self._pending[chan] = value
            if self._flush is None:
                self._flush = self.hass.async_create_task(self._run())
            flush = self._flush
        await flush

    async def _run(self):
        await asyncio.sleep(BATCH_WINDOW)
        async with self._gate:
            # Anything arriving from here on belongs to the next write.
            pending, self._pending = self._pending, {}
            self._flush = None
        await self.hass.async_add_executor_job(self._write, pending)

    def _write(self, pending):
        """Read the port, apply the changes, write it back, check it took."""
        channel = self._channel
        wanted = channel.read_port()
        mask = 0
        for chan, value in pending.items():
            bit = 1 << (chan - 1)
            mask |= bit
            wanted = wanted | bit if value else wanted & ~bit

        for attempt in range(1, WRITE_ATTEMPTS + 1):
            channel.write_port(wanted)
            got = channel.read_port()
            if got & mask == wanted & mask:
                if attempt > 1:
                    _LOGGER.warning(
                        "%s port on card %s needed %s attempts",
                        channel.entity_type, card_from_stack(channel.stack),
                        attempt,
                    )
                return
            time.sleep(WRITE_SETTLE * attempt)

        raise SMApiError(
            f"{channel.entity_type} port on card {card_from_stack(channel.stack)} "
            f"still reads "
            f"{got:#04x} after {WRITE_ATTEMPTS} attempts to write {wanted:#04x}"
        )


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
        _LOGGER.error(
            "Skipping %s_%s on card %s: %s",
            entity_type, chan, card_from_stack(stack), err,
        )
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
    """Identity and naming, shared by all platforms."""

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
            f"{NAME_PREFIX}{card_from_stack(channel.stack)}"
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
            writer = _port_writer(self.hass, self._sm_channel)
            if writer is not None and len(values) == 1:
                # Batched with whatever else is switching on this card.
                await writer.set(self._sm_channel.chan, values[0])
            else:
                await self.hass.async_add_executor_job(
                    self._sm_channel.set, *values
                )
        except Exception as ex:  # noqa: BLE001 - the vendor library raises bare
            # OSError/IOError on bus trouble.
            _LOGGER.error("Writing %s failed: %s", self._sm_channel, ex)
            raise HomeAssistantError(f"Writing {self._sm_channel} failed: {ex}") from ex
        # Any sweep already under way read the card before this, so mark the
        # moment before asking for a fresh one.
        self._sm_written_at = time.monotonic()
        await self.coordinator.async_request_refresh()
