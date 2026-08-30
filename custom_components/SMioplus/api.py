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

from .const import COM_NOGET
from .data import API, SM_MAP

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
        return self._get is not None

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
