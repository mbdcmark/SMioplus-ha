"""One poller per card and interval, so the bus is read in a single sweep.

Before this, every entity polled the card on its own executor thread: forty
odd threads issuing interleaved I2C transactions on one bus.  Now a single job
walks the registered channels once per interval and hands the result to every
entity that asked for it.
"""

import asyncio
import logging
import time
from datetime import timedelta
from inspect import signature

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BUS_SETTLE, READ_TOLERANCE
from .data import DOMAIN

_LOGGER = logging.getLogger(__name__)

# How often at most to complain that a sweep overran its interval.  Once ever
# is too quiet: adding cards later changes the arithmetic.
SLOW_WARN_EVERY = 300.0


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
        self._slow_warned_at = 0.0
        self._failures = {}
        self._sweep_lock = asyncio.Lock()
        # When the sweep now being reported started reading the card.  An
        # entity compares this against its own last write to tell a stale
        # answer from a current one.
        self.sweep_started = 0.0

    def register(self, channel):
        """Include ``channel`` in every sweep from now on."""
        if channel.readable:
            self._channels[channel.key] = channel

    async def _async_update_data(self):
        # One sweep at a time.  sweep_started has to describe the data being
        # handed to the entities: if two sweeps overlapped, a stale answer
        # could pass the check that keeps a write from being undone.
        async with self._sweep_lock:
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

    def _hold(self, key, channel, previous):
        """Keep the last good value for a few sweeps before giving up on it."""
        count = self._failures.get(key, 0) + 1
        self._failures[key] = count
        if count < READ_TOLERANCE and key in previous:
            return previous[key]
        if count == READ_TOLERANCE:
            _LOGGER.warning(
                "%s has failed %s reads running; reporting it unavailable",
                channel, count,
            )
        return None

    def _read_all(self):
        """Read every channel. Runs in an executor; each call locks the bus."""
        started = self.sweep_started = time.monotonic()
        previous = self.data or {}
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
            failed = False
            value = None
            try:
                if channel.bulk:
                    port = channel.entity_type
                    if port not in ports:
                        if transactions and BUS_SETTLE:
                            time.sleep(BUS_SETTLE)
                        transactions += 1
                        ports[port] = self._read_bulk(channel)
                    raw = ports[port]
                    if raw is None:
                        failed = True
                    else:
                        value = channel.decode(raw)
                else:
                    if transactions and BUS_SETTLE:
                        time.sleep(BUS_SETTLE)
                    transactions += 1
                    value = channel.get()
            except Exception as ex:  # noqa: BLE001 - one bad channel must not
                # take the rest of the card down with it.
                _LOGGER.error("Reading %s failed: %s", channel, ex)
                failed = True

            if failed:
                values[key] = self._hold(key, channel, previous)
            else:
                self._failures.pop(key, None)
                values[key] = value

        if values and all(value is None for value in values.values()):
            raise UpdateFailed(f"Card on stack {self.stack} did not answer")

        elapsed = time.monotonic() - started
        if elapsed > self.interval and started - self._slow_warned_at > SLOW_WARN_EVERY:
            # Rate limited: at a tenth of a second this would flood the log.
            self._slow_warned_at = started
            _LOGGER.warning(
                "Reading %s channel(s) on stack %s took %.3fs in %s bus "
                "transaction(s), longer than the %.3fs interval asked for. "
                "Raise update_interval or poll fewer channels.",
                len(values), self.stack, elapsed, transactions, self.interval,
            )
        return values
