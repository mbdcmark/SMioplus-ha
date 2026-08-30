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

- Simple first card config:

```yaml
SMioplus:
```

- One specific card:

```yaml
SMioplus:
    - stack: 3
```

- Several cards:

```yaml
SMioplus:
    - stack: 1
    - stack: 3
    - stack: 4
```

- Only specific entities, per card:

> !The following example is provided for illustrative purposes only and does NOT necessarily represent real entities!

```yaml
SMioplus:
    - stack: 1
      relay_1:
      relay_3:
      opto_1:
        update_interval: 0.1
    - stack: 3
      relay:
        chan_range: "1..8"
      opto_cnt:
        chan_range: "2..6"
        update_interval: 0.1
```

[//]: # (__CUSTOM_README__ START)
[//]: # (__CUSTOM_README__ END)

### Card numbering

Cards count from 1 everywhere you look: `stack: 1` is the first card, its
entities are `smio1_relay_1` and so on, and the log calls it card 1. The
jumpers and the I2C addresses count from 0, because that is what the hardware
does, and nothing else asks you to.

So the first card has its jumpers set to level 0 and is written `stack: 1`;
the eighth is at level 7 and is written `stack: 8`. `STACK_OFFSET` in `data.py`
is the single place that decides this -- set it to 0 to count from 0
throughout, as the jumpers do.

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
are unknown entity names and card numbers outside 1..8.

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
    - stack: 1
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
workable. If a sweep overruns its interval the log says so, naming the measured
time and how many bus transactions it took -- but not for the first half minute
after starting, when binding 384 channels, configuring the edge counters and
reading the revisions puts well over a second of traffic on the bus that a fast
poller has to wait behind. Should reads start failing on a long or noisy bus, raise
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

The address and bus are `BASE_ADDRESS + stack` and `I2C_BUS` in `data.py`, the
stack being the jumper level rather than the card number,
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

The window is zero. Home Assistant fires the eight service calls in one event
loop tick, so handing the loop back once already finds them queued -- waiting
any longer would buy nothing and delay every single switch by that much. If the
calls ever arrive spread out the batch splits into two writes, which is what
happened before batching existed. Types without a `set_all` -- the dimmers -- are written
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


### Polling faster than once a second

`DataUpdateCoordinator` plans its next sweep at `int(now) + interval`, truncated
to whole seconds. At an interval below one second that lands in the past, the
timer fires at once, plans another moment in the past, and the card is read as
fast as the bus allows -- hundreds of times a second, saturating the bus and a
CPU core while the log insists it is polling at 0.1s.

Intervals under a second are therefore driven by a timer of this integration's
own, started with the first entity that listens. Everything else is left to the
coordinator, which handles whole seconds correctly.


### Which card is in the stack

Each card reports its own revisions in registers 0x78 to 0x7B, and the
integration reads them once per card at startup:

```
card 1: hardware 3.0, firmware 1.4
```

Worth knowing because the vendor's own tool gates its PWM frequency commands
(`pwmfrd`, `pwmfwr`) on hardware 3.0 or newer: below that, the open drain
outputs run at a fixed frequency. That is the only version-dependent behaviour
in the vendor sources, and this integration does not use those commands, so
older cards lose nothing here.


### Setting the intervals from configuration.yaml

Editing `data.py` does not survive a HACS update, so how often each type is
read can be set per card with an `intervals` block:

```yaml
SMioplus:
  - stack: 1
    intervals:
      opto: 0.1
      adc: 30
```

Unlike naming an entity, this does not narrow down which entities are loaded:
every channel of every type still comes up. A type left out keeps the default
from the card description, and a per-entity `update_interval` still wins over
both.

A card needs nothing but its number, so name an interval only where it should
differ. `examples/sequent.yaml` shows both that and the fuller form. If you do
reach for a YAML anchor to save repetition, give each one its own name: an
alias takes the most recent anchor of that name above it, so reusing a name
quietly hands later cards the wrong block. Point `configuration.yaml` at the
file with:

```yaml
SMioplus: !include sequent.yaml
```
