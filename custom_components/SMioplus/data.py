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
        }
    },
    "number": {
        "dac": {
                "chan_no": 4,
                "uom": "V",
                "device_class": "voltage",
                "min_value": 0.0,
                "max_value": 10.0,
                "step": 0.01,
                "com": {
                    "get": "getDacV",
                    "set": "setDacV"
                },
                "icon": {
                    "on": "mdi:flash-triangle",
                    "off": "mdi:flash-triangle"
                }
        },
        "od": {
                "chan_no": 4,
                "uom": "%",
                "min_value": 0.0,
                "max_value": 100.0,
                "step": 0.01,
                "com": {
                    "get": "_fixed_getOdPwm",
                    "set": "_fixed_setOdPwm"
                },
                "icon": {
                    "on": "mdi:percent",
                    "off": "mdi:percent"
                }
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
