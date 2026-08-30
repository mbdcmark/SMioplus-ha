"""Sequent Microsystems Home Automation Integration."""

import logging

import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform

from . import data
from .const import (  # noqa: F401  (re-exported for compatibility)
    COM_NOGET,
    CONF_CHAN,
    CONF_CHAN_RANGE,
    CONF_CHANNELS,
    CONF_NAME,
    CONF_STACK,
    CONF_TYPE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)

DOMAIN = data.DOMAIN
NAME_PREFIX = data.NAME_PREFIX
card_from_stack = data.card_from_stack
stack_from_card = data.stack_from_card
SM_MAP = data.SM_MAP
SM_API = data.API
PLATFORM_FOR_TYPE = data.PLATFORM_FOR_TYPE

_LOGGER = logging.getLogger(__name__)

ENTITY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CHANNELS): cv.string,
        vol.Optional(CONF_CHAN_RANGE): cv.string,
        vol.Optional(CONF_UPDATE_INTERVAL): vol.All(
            vol.Coerce(float), vol.Range(min=MIN_UPDATE_INTERVAL)
        ),
    }
)

# The entity keys are card specific (relay_1, opto_cnt, ...), so they cannot be
# spelled out here; they are validated against SM_MAP in async_setup instead.
CARD_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_STACK, default=card_from_stack(data.MIN_STACK)): vol.All(
            vol.Coerce(int),
            vol.Range(
                min=card_from_stack(data.MIN_STACK),
                max=card_from_stack(data.MAX_STACK),
            ),
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

# ensure_list turns a bare `SMioplus:` (which YAML gives us as None) into an
# empty list, and a single mapping into a one card list.
CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [CARD_SCHEMA])}, extra=vol.ALLOW_EXTRA
)


def _entity_name(stack, entity_type, chan):
    return f"{NAME_PREFIX}{card_from_stack(stack)}_{entity_type}_{chan}"


def _discovery_info(stack, entity_type, chan, update_interval):
    return {
        CONF_NAME: _entity_name(stack, entity_type, chan),
        CONF_STACK: stack,
        CONF_TYPE: entity_type,
        CONF_CHAN: chan,
        CONF_UPDATE_INTERVAL: update_interval,
    }


def _parse_channels(value):
    """Parse a channel list: 1,3,5 -> [1, 3, 5]."""
    return [int(part) for part in str(value).split(",") if part.strip()]


def _parse_chan_range(value):
    """Parse a channel range: 2..6 -> [2, 3, 4, 5, 6]."""
    start, end = str(value).split("..", 1)
    return list(range(int(start), int(end) + 1))


def _chan_count(entity_type):
    """How many channels the card has of this entity type."""
    return int(SM_MAP[PLATFORM_FOR_TYPE[entity_type]][entity_type]["chan_no"])


def _load(hass, config, stack, entity_type, chans, update_interval):
    """Queue one platform load per requested channel."""
    platform = PLATFORM_FOR_TYPE[entity_type]
    chan_no = _chan_count(entity_type)
    for chan in chans:
        if not 1 <= chan <= chan_no:
            _LOGGER.error(
                "%s has channels 1..%s, so channel %s does not exist",
                entity_type, chan_no, chan,
            )
            continue
        hass.async_create_task(
            async_load_platform(
                hass,
                platform,
                DOMAIN,
                _discovery_info(stack, entity_type, chan, update_interval),
                config,
            )
        )


def _load_whole_card(hass, config, stack):
    """Load every entity the card has."""
    for platform, entities in SM_MAP.items():
        for entity_type, spec in entities.items():
            if spec.get("optional", False):
                continue
            _load(
                hass, config, stack, entity_type,
                range(1, int(spec["chan_no"]) + 1), None,
            )


def _setup_entity(hass, config, stack, entity_key, options):
    """Work out which channels `entity_key` asks for, and load them."""
    try:
        options = ENTITY_SCHEMA(options or {})
    except vol.Invalid as err:
        _LOGGER.error("Bad options for %s: %s", entity_key, err)
        return

    channels = options.get(CONF_CHANNELS)
    chan_range = options.get(CONF_CHAN_RANGE)
    update_interval = options.get(CONF_UPDATE_INTERVAL)

    # Three ways to name channels, checked in order.  This used to be three
    # nested bare `except:` blocks, which meant a failure part way through one
    # form silently fell through to the next and half applied the config.
    if channels is not None:
        entity_type = entity_key
        try:
            chans = _parse_channels(channels)
        except ValueError:
            _LOGGER.error("%s: channels %r is not a comma separated list of "
                          "channel numbers", entity_key, channels)
            return
    elif chan_range is not None:
        entity_type = entity_key
        try:
            chans = _parse_chan_range(chan_range)
        except ValueError:
            _LOGGER.error("%s: chan_range %r is not of the form \"start..end\"",
                          entity_key, chan_range)
            return
    elif entity_key in PLATFORM_FOR_TYPE:
        # A bare `relay:` means every channel that type has.
        entity_type = entity_key
        chans = None
    else:
        entity_type, _, chan = entity_key.rpartition("_")
        try:
            chans = [int(chan)]
        except ValueError:
            _LOGGER.error("%s doesn't respect type_channel format", entity_key)
            return

    if entity_type not in PLATFORM_FOR_TYPE:
        _LOGGER.error(
            "%s is not an entity of this card; known entities are %s",
            entity_type, ", ".join(sorted(PLATFORM_FOR_TYPE)),
        )
        return

    if chans is None:
        chans = range(1, _chan_count(entity_type) + 1)

    _load(hass, config, stack, entity_type, chans, update_interval)


async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {})

    card_configs = config.get(DOMAIN)
    if not card_configs:
        _load_whole_card(hass, config, data.MIN_STACK)
        return True

    for card_config in card_configs:
        # Copy: this is Home Assistant's config object, not ours to edit.
        card_config = dict(card_config)
        # `stack:` is a card number; the hardware counts from zero.
        stack = stack_from_card(
            int(card_config.pop(CONF_STACK, card_from_stack(data.MIN_STACK)))
        )
        if not card_config:
            _load_whole_card(hass, config, stack)
            continue
        for entity_key, options in card_config.items():
            _setup_entity(hass, config, stack, entity_key, options)

    return True
