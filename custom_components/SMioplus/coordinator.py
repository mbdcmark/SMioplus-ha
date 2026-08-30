"""One poller per card and interval, so the bus is read in a single sweep.

Before this, every entity polled the card on its own executor thread: forty
odd threads issuing interleaved I2C transactions on one bus.  Now a single job
walks the registered channels once per interval and hands the result to every
entity that asked for it.
"""

import logging
import time
from datetime import timedelta
from inspect import signature

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BUS_SETTLE
from .data import DOMAIN

_LOGGER = logging.getLogger(__name__)


def async_get_coordinator(hass, stack, interval):
    """Return the coordinator polling ``stack`` every ``interval`` seconds."""
    coordinators = hass.data.setdefault(DOMAIN, {})
    key = (stack, interval)
    if key not in coordinators:
        coordinators[key] = SMCoordinator(hass, stack, interval)
    return coordinators[key]


class SMCoordinator(DataUpdateCoordinator):
    """Reads every registered channel of one card in a single pass."""

    def __init__(self, hass, stack, interval):
        kwargs = {}
        # Newer cores take config_entry explicitly and otherwise guess it from
        # the task context.  This integration is YAML only, so say so.
        if "config_entry" in signature(DataUpdateCoordinator.__init__).parameters:
            kwargs["config_entry"] = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} stack {stack} every {interval}s",
            update_interval=timedelta(seconds=interval),
            # Ten sweeps a second mostly read back what the last one did.
            # Waking every entity for an unchanged value is pure cost.
            always_update=False,
            **kwargs,
        )
        self.stack = stack
        self.interval = interval
        self._channels = {}
        self._slow_warned = False
        # When the sweep now being reported started reading the card.  An
        # entity compares this against its own last write to tell a stale
        # answer from a current one.
        self.sweep_started = 0.0

    def register(self, channel):
        """Include ``channel`` in every sweep from now on."""
        if channel.readable:
            self._channels[channel.key] = channel

    async def _async_update_data(self):
        return await self.hass.async_add_executor_job(self._read_all)

    def _read_bulk(self, channel):
        """One whole-port read, or None if it failed."""
        try:
            return channel.read_bulk()
        except Exception as ex:  # noqa: BLE001 - the vendor library raises bare
            # OSError/IOError on bus trouble.
            _LOGGER.error(
                "Reading all %s on stack %s failed: %s",
                channel.entity_type, channel.stack, ex,
            )
            return None

    def _read_all(self):
        """Read every channel. Runs in an executor; each call locks the bus."""
        started = self.sweep_started = time.monotonic()
        values = {}

        # getOptoCh() is getOpto() plus a bit shift, and getRelayCh() is
        # getRelays() plus a bit shift, so asking per channel repeated the same
        # transaction eight times over and threw seven eighths of each answer
        # away.  One read per port per sweep instead.
        ports = {}
        transactions = 0

        # Snapshot: entities keep registering from the event loop while this
        # runs in an executor thread, and iterating the live dict raises
        # "dictionary changed size during iteration" right after a restart.
        # Anything added mid-sweep is picked up by the next one.
        for key, channel in list(self._channels.items()):
            try:
                if channel.bulk:
                    port = (channel.stack, channel.entity_type)
                    if port not in ports:
                        if transactions and BUS_SETTLE:
                            time.sleep(BUS_SETTLE)
                        ports[port] = self._read_bulk(channel)
                        transactions += 1
                    raw = ports[port]
                    values[key] = None if raw is None else channel.decode(raw)
                else:
                    if transactions and BUS_SETTLE:
                        time.sleep(BUS_SETTLE)
                    values[key] = channel.get()
                    transactions += 1
            except Exception as ex:  # noqa: BLE001 - one bad channel must not
                # take the rest of the card down with it.
                _LOGGER.error("Reading %s failed: %s", channel, ex)
                values[key] = None

        if values and all(value is None for value in values.values()):
            raise UpdateFailed(f"Card on stack {self.stack} did not answer")

        elapsed = time.monotonic() - started
        if elapsed > self.interval and not self._slow_warned:
            # Once is enough; at a tenth of a second this would flood the log.
            self._slow_warned = True
            _LOGGER.warning(
                "Reading %s channel(s) on stack %s took %.3fs in %s bus "
                "transaction(s), longer than the %.3fs interval asked for. "
                "Raise update_interval or poll fewer channels.",
                len(values), self.stack, elapsed, transactions, self.interval,
            )
        return values
