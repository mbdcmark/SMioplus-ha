"""Configuration vocabulary and tuning constants.

Everything in here is generic to the Sequent Microsystems integrations; the
card specific description lives in :mod:`.data`.
"""

from homeassistant.const import CONF_NAME  # noqa: F401  (re-exported)

CONF_STACK = "stack"
CONF_TYPE = "type"
CONF_CHAN = "chan"
CONF_CHANNELS = "channels"
CONF_CHAN_RANGE = "chan_range"
CONF_UPDATE_INTERVAL = "update_interval"  # In seconds
CONF_INTERVALS = "intervals"  # Per entity type, for a whole card

# Marker for cards whose hardware cannot be read back; the last written value
# is reported instead.
COM_NOGET = "__NOGET__"

DEFAULT_UPDATE_INTERVAL = 60.0

# Polling faster than this hammers the I2C bus without giving anything back.
MIN_UPDATE_INTERVAL = 0.05

# Seconds to wait between two bus transactions.  Version 1.x slept 50ms at the
# top of every entity's update(), because forty entities polled the card from
# their own threads and the transactions interleaved.  The bus lock in api.py
# now serialises them properly, so the wait buys nothing and would put a floor
# of ~0.35s under an eight channel sweep.  Raise it only if reads start failing
# on a long or noisy bus.
BUS_SETTLE = 0.0

# Set False to make every read go through the vendor library, ignoring the
# direct register path in api.py.
USE_DIRECT_BUS = True

# Seconds to keep the next transaction off a card after writing to it, so the
# firmware has acted before anything else reaches it.  Reads are safe without
# it, but the relay set/clear registers are commands the card has to carry out.
# It is a per card wait, not a bus wide one: the other cards are separate
# devices and are read straight through it.
WRITE_SETTLE = 0.01

# How many times to write a verified command before giving up.  The relay
# set/clear registers are fire and forget: the card acknowledges the I2C
# transfer, not the switching, so a lost command is silent.
WRITE_ATTEMPTS = 3

# Seconds to gather channel writes before sending them as one transaction.
# Zero: Home Assistant fires the eight service calls in one event loop tick, so
# handing the loop back once already finds them queued.  Waiting any longer
# would buy nothing and cost every single switch that much delay.  Should the
# calls ever arrive spread out, the batch simply splits into two writes, which
# is what it did before batching existed.
BATCH_WINDOW = 0.0

# How many sweeps in a row a channel may fail before it is reported
# unavailable.  A single failed read is usually the bus being busy, not the
# card being gone, and flicking every entity to unavailable over it is worse
# than holding the last value for another sweep or two.
READ_TOLERANCE = 3

# ...and never hold a stale value longer than this, however slow the poller.
# Three sweeps of a minute is three minutes of reporting a reading nobody took.
READ_HOLD_SECONDS = 30.0
