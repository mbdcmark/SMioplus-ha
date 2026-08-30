"""Description of the Home Automation card.

This is the only card specific file: it says which entities the card exposes,
on which Home Assistant platform they belong, and which library calls drive
them.  Everything else in the integration is generic.
"""

FULL_NAME = "Home Automation"
LINK = "https://sequentmicrosystems.com/products/raspberry-pi-home-automation-card"
MANUFACTURER = "Sequent Microsystems"

import libioplus

API = libioplus

# Mirrors of the vendor library's own constants, used by the direct register
# path in api.py.  It checks itself against the library before trusting them,
# so a mismatch costs speed rather than correctness.
I2C_BUS = 1
BASE_ADDRESS = 0x28
DOMAIN = "SMioplus"
NAME_PREFIX = "smio"

# Stack levels selectable with the card's jumpers.
MIN_STACK = 0
MAX_STACK = 7

SM_MAP = {
    "button": {
        "opto_cnt_rst": {
            "chan_no": 8,
            "com": {
                "set": "rstOptoCount",
            },
        }
    },
    "binary_sensor": {
        "opto": {
                "chan_no": 8,
                # An input is useless at the 30s default.  One bulk read now
                # covers all eight channels, so this is a single transaction
                # per card per sweep.  Overridable per entity from
                # configuration.yaml.
                "update_interval": 0.1,
                "com": {
                    "get": "getOptoCh",
                    # One transaction for all eight; getOptoCh is this plus
                    # a bit shift.
                    "get_all": "getOpto",
                },
                "register": 3,
                "icon": {
                    "on": "mdi:numeric-1",
                    "off": "mdi:numeric-0",
                }
        },
    },
    "sensor":  {
        "opto_cnt": {
                "chan_no": 8,
                "uom": "",
                "precision": 0,
                # Counting up until the matching reset button clears it.
                "state_class": "total_increasing",
                "com": {
                    "get": "getOptoCount",
                },
                # The card counts nothing until an edge is selected, so
                # getOptoCount would return 0 for ever.  0 none, 1 rising,
                # 2 falling, 3 both.
                "init": {"cfgOptoEdgeCount": 1},
        },
        "adc": {
                "chan_no": 8,
                "uom": "V",
                "device_class": "voltage",
                "state_class": "measurement",
                # 12-bit over 0..10V, so millivolts are meaningful.
                "precision": 3,
                "com": {
                    "get": "getAdcV",
                },
                "icon": {
                    "on": "mdi:flash-triangle",
                    "off": "mdi:flash-triangle"
                }
        },
    },
    "switch": {
        "relay": {
                "chan_no": 8,
                "com": {
                    "get": "getRelayCh",
                    "get_all": "getRelays",
                    "set": "setRelayCh"
                },
                "register": 0,
                # setRelayCh writes to a set/clear register and the card
                # acknowledges the transfer, not the switching, so a lost
                # command is silent.  Read it back.
                "verify": True,
        }
    },
    # Both analog outputs drive dimmers: the open drain channels are PWM, and
    # 0-10V is what a 0-10V dimmer expects.  min_value and max_value are the
    # ends of the brightness scale.
    "light": {
        "dac": {
                "chan_no": 4,
                "min_value": 0.0,
                "max_value": 10.0,
                "com": {
                    "get": "getDacV",
                    "set": "setDacV"
                },
        },
        "od": {
                "chan_no": 4,
                "min_value": 0.0,
                "max_value": 100.0,
                "com": {
                    "get": "_fixed_getOdPwm",
                    "set": "_fixed_setOdPwm"
                },
        },
    },
}

PLATFORMS = tuple(SM_MAP)

# Entity type -> the platform it is served by.  Entity type names are unique
# across platforms, which is what lets `relay_1:` in configuration.yaml be
# resolved without the user naming a platform.
PLATFORM_FOR_TYPE = {
    entity_type: platform
    for platform, entities in SM_MAP.items()
    for entity_type in entities
}
