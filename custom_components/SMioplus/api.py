"""Binding layer between the card description and the vendor library.

The vendor libraries come in two shapes:

* a module whose functions take the stack level first --
  ``getRelayCh(stack, chan)``, ``setRelayCh(stack, chan, value)``
* a class constructed with the stack level --
  ``Card(stack).getRelayCh(chan)``

and on cards that only have one of something, the channel argument is dropped
altogether.  Instead of every platform re-deriving that, all access goes
through :class:`SMChannel`, which resolves the calling convention once at
setup and raises :class:`SMApiError` when the library does not match what the
card description asks for -- rather than silently picking the wrong form.
"""

import inspect
import logging
import threading
from inspect import signature

try:
    import smbus2
except ImportError:  # the vendor library depends on it, so this is unusual
    smbus2 = None

from .const import COM_NOGET, USE_DIRECT_BUS
from .data import API, BASE_ADDRESS, I2C_BUS, SM_MAP

_LOGGER = logging.getLogger(__name__)

# Every card on the machine shares one I2C bus, and the vendor library is not
# thread safe.  All transactions are taken under this lock so that reads and
# writes from different entities cannot interleave.
BUS_LOCK = threading.RLock()

# How many value arguments a `set` command takes, per platform.  A button only
# carries out an action; everything else writes a value.
_SET_VALUE_ARGS = {"button": 0}
_DEFAULT_SET_VALUE_ARGS = 1

# One API object per stack level, instead of one per entity.
_TARGETS: dict[int, object] = {}


class SMApiError(Exception):
    """The vendor library does not provide what the card description asks for."""


class _Bus:
    """One SMBus handle, held open for the life of the process.

    The vendor library opens and closes /dev/i2c-N around every single call,
    which costs far more than the transfer itself: eight opto channels measured
    0.111s on a Pi 5 for what is one register read. Holding the handle open
    puts that same read well under a millisecond, which is the difference
    between one card and eight at a tenth of a second.
    """

    def __init__(self):
        self._handle = None

    def close(self):
        handle, self._handle = self._handle, None
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass

    def read_stable(self, address, register, retries=10):
        """Read until two reads agree, as the vendor library does.

        The card can answer while it is updating the register, so a single
        read is not trustworthy.
        """
        with BUS_LOCK:
            try:
                if self._handle is None:
                    self._handle = smbus2.SMBus(I2C_BUS)
                previous = None
                for _ in range(retries):
                    value = self._handle.read_byte_data(address, register)
                    if value == previous:
                        return value
                    previous = value
            except OSError:
                # Drop the handle so the next call reopens it.
                self.close()
                raise
        raise SMApiError(
            f"register {register} at {address:#04x} never read the same twice"
        )


_BUS = _Bus()
_PORTS = {}


class _FastPort:
    """A direct register read standing in for a vendor whole-port call.

    Checked against the vendor call before it is trusted. If the two disagree
    the register description is wrong for this card, and the fast path retires
    itself rather than reporting fiction.
    """

    def __init__(self, stack, register, vendor, label):
        self._address = BASE_ADDRESS + stack
        self._register = register
        self._vendor = vendor
        self._label = label
        self._checks_left = 3
        self._enabled = (
            USE_DIRECT_BUS and smbus2 is not None and register is not None
        )

    def read(self):
        if not self._enabled:
            return self._vendor()
        try:
            value = _BUS.read_stable(self._address, self._register)
        except Exception as ex:  # noqa: BLE001 - any bus trouble at all
            _LOGGER.warning(
                "%s: direct read failed (%s); staying with the library",
                self._label, ex,
            )
            self._enabled = False
            return self._vendor()
        if self._checks_left:
            return self._checked(value)
        return value

    def _checked(self, value):
        """Compare against the vendor call, allowing for a genuine change."""
        try:
            reference = self._vendor()
        except Exception:  # noqa: BLE001 - nothing to compare against
            return value
        if reference == value:
            self._checks_left = 0
            _LOGGER.debug("%s: direct register read verified", self._label)
            return value
        self._checks_left -= 1
        if not self._checks_left:
            self._enabled = False
            _LOGGER.warning(
                "%s: direct read gave %s where the library gave %s, three "
                "times over; staying with the library",
                self._label, value, reference,
            )
        # Trust the library for as long as the two still disagree.
        return reference


def _fast_port(spec, stack, entity_type, vendor):
    """The shared direct-read port for one entity type on one card."""
    key = (stack, entity_type)
    with BUS_LOCK:
        if key not in _PORTS:
            _PORTS[key] = _FastPort(
                stack, spec.get("register"), vendor,
                f"{entity_type} on stack {stack}",
            )
        return _PORTS[key]


def _arity(func):
    """Number of arguments ``func`` takes, or None when it cannot be told."""
    try:
        return len(signature(func).parameters)
    except (TypeError, ValueError):
        return None


def _target(stack):
    """The object carrying the card's methods for ``stack``.

    Constructing a class based API talks to the bus, so this must be called
    from an executor thread, never from the event loop.
    """
    if not inspect.isclass(API):
        return API
    with BUS_LOCK:
        if stack not in _TARGETS:
            _TARGETS[stack] = API(stack)
        return _TARGETS[stack]


class SMChannel:
    """A single hardware channel with its get/set bound to the vendor library.

    Constructing this touches the bus, so build it in an executor job.
    """

    def __init__(self, platform, entity_type, stack, chan):
        spec = SM_MAP[platform][entity_type]
        self.platform = platform
        self.entity_type = entity_type
        self.stack = stack
        self.chan = chan
        self.key = (stack, entity_type, chan)
        self._get = self._bind_com(spec, "get", 0)
        self._set = self._bind_com(
            spec, "set", _SET_VALUE_ARGS.get(platform, _DEFAULT_SET_VALUE_ARGS)
        )
        # One call that answers for every channel of this type on the card.
        # The arity check works this out on its own: getOpto(stack) takes no
        # channel, so it binds without one.
        self._get_all = self._bind_com(spec, "get_all", 0)
        # Shared per entity type per card, so the check against the library
        # happens once rather than eight times.
        self._port = (
            _fast_port(spec, stack, entity_type, self._get_all)
            if self._get_all is not None
            else None
        )
        self._configure(spec)

    def __str__(self):
        return f"{self.entity_type}_{self.chan} on stack {self.stack}"

    def _configure(self, spec):
        """Run the one-off commands this channel needs before it works.

        The edge counters are the reason this exists: the card counts nothing
        until an edge is selected, so getOptoCount would return 0 forever.
        """
        for name, value in spec.get("init", {}).items():
            args = tuple(value) if isinstance(value, (list, tuple)) else (value,)
            self._bind(name, len(args))(*args)

    def _bind_com(self, spec, action, value_args):
        name = spec["com"].get(action)
        if not name or name == COM_NOGET:
            # The card cannot do this; the entity falls back to reporting the
            # last value it wrote.
            return None
        return self._bind(name, value_args)

    def _bind(self, name, value_args):
        """Resolve a vendor function into a call for this channel."""
        target = _target(self.stack)
        try:
            func = getattr(target, name)
        except AttributeError:
            raise SMApiError(
                f"{API.__name__} has no command {name!r}, needed by {self}"
            ) from None

        # A module level function carries the stack level; a bound method does
        # not, because the instance already knows it.
        prefix = () if inspect.isclass(API) else (self.stack,)
        with_chan = len(prefix) + value_args + 1
        without_chan = len(prefix) + value_args

        arity = _arity(func)
        if arity is None:
            # *args, or a builtin with no introspectable signature.  Fall back
            # to the documented full form.
            uses_chan = True
        elif arity == with_chan:
            uses_chan = True
        elif arity == without_chan:
            uses_chan = False
        else:
            raise SMApiError(
                f"{name}() takes {arity} argument(s), but {self} needs it to take "
                f"{with_chan} (with channel) or {without_chan} (without)"
            )

        shape = [*(["stack"] if prefix else []), *(["chan"] if uses_chan else [])]
        shape += ["value"] * value_args
        _LOGGER.debug("%s: %s(%s)", self, name, ", ".join(shape))

        chan_arg = (self.chan,) if uses_chan else ()

        def call(*values):
            with BUS_LOCK:
                return func(*prefix, *chan_arg, *values)

        return call

    @property
    def readable(self):
        return self._get is not None or self._get_all is not None

    @property
    def bulk(self):
        """Whether this channel can be served by a whole-port read."""
        return self._get_all is not None

    def read_bulk(self):
        """Read the whole port. One result serves every channel of the type."""
        return self._port.read()

    def decode(self, raw):
        """Pick this channel out of a whole-port read."""
        return (int(raw) >> (self.chan - 1)) & 1

    @property
    def writable(self):
        return self._set is not None

    def get(self):
        if self._get is None:
            raise SMApiError(f"{self} cannot be read")
        return self._get()

    def set(self, *values):
        if self._set is None:
            raise SMApiError(f"{self} cannot be written")
        return self._set(*values)
