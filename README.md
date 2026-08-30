# Sequent Microsystems Home Automation Home Assistant Integration

Integrate [Home Automation](https://sequentmicrosystems.com/products/raspberry-pi-home-automation-card)
seamlessly with Home Assistant, bringing all your custom functionality into the Home Assistant ecosystem for enhanced control, automation, and ease of use.



## Installation

> If you already have HACS, I2C and File editor configured, you can skip to [The actual installation](#the-actual-installation)


#### Video tutorials

- [Install HACS video](https://youtu.be/Fl3lATWhQVM) for step 1.
- [Enable I2C and Install file editor video](https://youtu.be/53Zj8NofS7k) for steps 2. and 3.
- [Install and config card drivers video](https://youtu.be/yH2HKjm7j24) for steps 4. and 5.

#### Prerequirements

1. Install HACS
    - Follow the official [instructions](https://www.hacs.xyz/docs/use/download/download/)

2. Install and run HassOS I2C Configurator add-on
    - Install [HassOS I2C Configurator](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fadamoutler%2FHassOSConfigurator)
    - Select your profile from the buttom left corner and enable `Advanced mode` in User settings
    - In Settings, Add-ons, Add-on Store, search and install `HassOS I2C Configurator`
    - Disable `Protection mode`
    - Start the add-on

3. Install File editor add-on
    - In Settings, Add-ons, Add-on Store, search and install `File editor`
    - Enable `Show in sidebar`
(see multiple config options bellow)


### The actual installation

4. Install SMioplus-ha from HACS
    - Open HACS (from the sidebar)
    - Click on the 3 dots in the top right corner and select `Custom repositories`
    - Repository is `SequentMicrosystems/SMioplus-ha` and type is `Integration`
    - Once added, you can now search it in HACS menu and download it

5. Add SMioplus config in configuration.yaml
    - In the sidebar, select `File editor` and start the add-on
    - Click the folder icon from the top left corner and edit `configuration.yaml`
    - At the end of the file append the SMioplus config:
        ```yaml
        SMioplus:
        ```
        > for more information, see [configuration.yaml](#configuration.yaml)
    - Save the file

6. Reboot system

7. Reboot system (yes, it must be done twice)



## configuration.yaml

`configuration.yaml` example:
```yaml
# Loads default set of integrations. Do not remove.
default_config:

# Load frontend themes from the themes folder
frontend:
  themes: !include_dir_merge_named themes

automation: !include automations.yaml
script: !include scripts.yaml
scene: !include scenes.yaml

SMioplus:
    # + optional configs
```

- Simple stack 0 config:

```yaml
SMioplus:
```

- Specific stack config:

```yaml
SMioplus:
    - stack: 2
```

- Multiple cards on different stack levels:

```yaml
SMioplus:
    - stack: 0
    - stack: 2
    - stack: 3
```

- Only specific entities for different stack levels:

> !The following example is provided for illustrative purposes only and does NOT necessarily represent real entities!

```yaml
SMioplus:
    - stack: 0
      relay_1:
      relay_3:
      opto_1:
        update_interval: 0.1
    - stack: 2
      relay:
        chan_range: "1..8"
      opto_cnt:
        chan_range: "2..6"
        update_interval: 0.1
```

[//]: # (__CUSTOM_README__ START)
[//]: # (__CUSTOM_README__ END)

### `configuration.yaml` entities

Possible entities:
```yaml
opto_cnt_rst_1: -> opto_cnt_rst_8:  (type: button)
dac_1: -> dac_4:  (type: light)
od_1: -> od_4:  (type: light)
adc_1: -> adc_8:  (type: sensor)
opto_cnt_1: -> opto_cnt_8:  (type: sensor)
opto_1: -> opto_8:  (type: binary_sensor)
relay_1: -> relay_8:  (type: switch)
```

Entity options:
- `chan_range: "start..end"` (inclusive channel range, e.g. `"2..6"`)
- `channels: "a,b,c"` (an explicit list of channels, e.g. `"1,3,5"`)
- `update_interval: seconds` (how often the card is read, default 30s; applies
  to every entity that has a value to read, so all of them except the buttons)

An entity named without a channel and without `channels` or `chan_range` --
just `relay:` -- means every channel that type has.

`chan_range` and `channels` are alternatives; when both are given, `channels`
wins. Channels the card does not have are reported in the log and skipped, as
are unknown entity names and stack levels outside 0..7.

Entities are not grouped under a device. Home Assistant only lets an entity
join the device registry by way of a config entry, and this integration is
configured from YAML; grouping them anyway earned a deprecation warning on
every start. It returns with a config flow.

Each card is read in a single pass per interval rather than once per entity, so
a card with 48 entities issues one sweep of I2C transactions every 30 seconds
instead of 48 independent ones.


## Upgrading from 1.x

Two changes are visible in your entity list.

1. `opto_1` .. `opto_8` are on/off inputs and have become `binary_sensor`s
   instead of `sensor`s, so `sensor.smio0_opto_1` is now
   `binary_sensor.smio0_opto_1`. Automations and dashboards naming those
   entities need updating. To keep the old behaviour, move the `opto` block in
   `custom_components/SMioplus/data.py` back under `"sensor"`.
2. Entities now have a stable, deterministic unique id. Version 1.x derived it
   from the entity id at startup, which could change on a reload and register
   the same channel a second time. The old registry entries are orphaned by the
   upgrade; remove any leftover duplicates once under Settings, Devices &
   services, Entities.


### Polling intervals

How often each entity type is read is part of the card description: every one
of them carries an `update_interval` in `custom_components/SMioplus/data.py`,
which is the one place to change it and needs no configuration.

| entity | read every |
| --- | --- |
| `opto` | 0.1s |
| `opto_cnt`, `adc`, `relay`, `dac`, `od` | 60s |
| `opto_cnt_rst` | never -- a button has nothing to read |

An input at 60 seconds feels broken, which is why the opto inputs are the
exception. The rest either change slowly or are written by Home Assistant
itself, which shows the new value immediately and only polls to confirm it.

To choose an interval yourself, name the entity and say so:

```yaml
SMioplus:
    - stack: 0
      adc:
        update_interval: 5
      opto:
      opto_cnt:
      opto_cnt_rst:
      relay:
      dac:
      od:
```

Naming any entity means only the named entities are loaded, which is why the
rest are listed too -- each on its own line, with no options, so they keep
whatever default they already had.

Each distinct interval gets its own poller, so the eight opto channels are read
in a sweep of their own rather than dragging the other forty along.

The bus lock serialises transactions, so there is no artificial wait between
them and eight channels read in a few milliseconds; 0.1 second intervals are
workable. If a sweep does overrun its interval the log says so once, naming the
measured time. Should reads start failing on a long or noisy bus, raise
`BUS_SETTLE` in `custom_components/SMioplus/const.py`.


### Counting opto pulses

The card counts edges in hardware, so `opto_cnt` catches pulses the polled
`opto` binary sensor would sleep through. It counts nothing until an edge is
selected, which the integration does for each channel at startup by way of the
entity's `init` block in `data.py`:

```python
"init": {"cfgOptoEdgeCount": 1},   # 0 none, 1 rising, 2 falling, 3 both
```

Rising gives one count per pulse; `3` counts both flanks and so counts twice.
The matching `opto_cnt_rst` button zeroes a channel.

`init` is generic: any entity may name vendor calls that have to run once,
before the channel will work.


### The direct register path

The vendor library opens and closes `/dev/i2c-1` around every single call. On a
Pi 5 that made one register read cost about 14ms, which is why eight opto
channels took 0.111s -- the transfer itself is a fraction of a millisecond. An
Arduino driving eight of these cards at 0.1s is not doing anything clever; it
simply keeps the bus open.

So does this integration, for the whole-port reads. An entity that names a
`register` is read straight from a `smbus2` handle held open for the life of
the process, using the same read-until-two-agree the library does:

```python
"get_all": "getOpto",
"register": 3,
```

The address and bus are `BASE_ADDRESS + stack` and `I2C_BUS` in `data.py`,
mirroring the library's own constants.

Hard-coded register numbers can go stale, so the fast path checks itself: the
first few reads are compared against the vendor call, and the library's answer
is the one reported until they agree. Three disagreements in a row and the fast
path retires itself with a line in the log. Any bus error does the same. Set
`USE_DIRECT_BUS = False` in `const.py` to switch it off outright.

Writes, and reads of anything without a `register`, still go through the
library.


### The analog outputs are dimmers

The open drain channels are PWM and the DAC channels are 0-10V, which is what a
0-10V dimmer expects, so both are lights rather than numbers. They behave the
way any other dimmer does: switching one off writes zero to the card but
remembers the level, and switching it back on returns to it. A light that has
never been on comes up at full.

The remembered level is published as a `brightness_when_on` attribute and read
back at startup, so it survives a restart even when the light was off at the
time and Home Assistant recorded no brightness of its own.

`min_value` and `max_value` in `data.py` are the ends of the brightness scale --
0..10 for the DACs, 0..100 for the open drains. To drive a channel by its raw
value instead, move its block back under `"number"`.


### Verified writes

`setRelayCh` writes to a set/clear register. The card acknowledges the I2C
transfer, not the switching, so a command it fails to act on is lost in
silence -- switching eight relays at once left some of them physically on.

An entity marked `"verify": True` in `data.py` is read back after every write
and retried if the card did not follow, waiting a little longer each time. If it
still has not followed after `WRITE_ATTEMPTS`, the service call fails with an
error instead of reporting a state the hardware does not have.

`WRITE_SETTLE` in `const.py` keeps the next transaction off that card for a
moment after each write, so the firmware has acted before anything else reaches
it. It is per card, not bus wide: writing to one card does not hold up reading
the others, which matters when eight of them are being polled ten times a
second. Raise it if the log starts reporting retries.


### Batched relay writes

Home Assistant calls `turn_on` and `turn_off` one entity at a time, so
switching eight relays used to arrive as eight separate transactions and they
closed in a visible cascade.

An entity type that names a `set_all` command has its writes gathered over
`BATCH_WINDOW` and sent as a single transaction: the port is read, the pending
bits applied, the whole byte written, and the result read back and retried the
way a single write is. The relays then switch together, and eight cards cost
eight transactions rather than sixty-four.

A single switch waits the same window before anything happens. Home Assistant
fires the eight service calls in one event loop tick, so they are all queued
long before it expires; the window only has to survive the scheduling, which is
why it is 10ms rather than something a person could feel. Types without a `set_all` -- the dimmers -- are written
one at a time as before.


### A failed read is not the same as a missing card

`getOpto` reads the port until two reads agree and gives up after ten tries, so
a busy bus or an input changing under it can fail a read that would have
succeeded a moment later. Flicking every channel on the card to unavailable
over that is worse than waiting: an automation watching a binary sensor sees a
jump to `unavailable` and back.

A channel that fails a read keeps its last value for `READ_TOLERANCE` sweeps or
`READ_HOLD_SECONDS`, whichever ends first, and the log says so when it gives
up. On the 0.1s opto poller that is three tenths of a second of holding still;
on the 60s poller the time cap ends it, because three sweeps there would be
three minutes of reporting a reading nobody took.
