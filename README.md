# Solar Airco

A Home Assistant custom integration (HACS) that steers air conditioners **for heating only**, based on your
solar production and the Solcast forecast.

## How it works

For every airco you configure, through entities in the UI:

| Entity | Meaning |
|---|---|
| Minimum temperature | Below this the airco heats from the grid, but only inside the time window |
| Desired temperature | Target while there is solar surplus |
| Heating window start / end | Heating is only allowed in this window (may cross midnight) |
| Priority | Lower number gets the solar surplus first |
| Controlled (switch) | Per-airco on/off for the controller |

Every minute (and whenever an airco changes state) the integration:

1. Combines actual PV production with the Solcast forecast (weight configurable) and subtracts house
   consumption to calculate the solar surplus. If the consumption sensor includes configured airco's in heat
   mode, their estimated current heating power is removed first.
2. Gives the surplus to the airco's in priority order. The estimated draw of an airco falls from its maximum to
   idle as the room approaches the desired temperature, so it needs less surplus to keep running.
3. Starts heating to the desired temperature on solar surplus, and stops when it is reached.
4. Below the minimum temperature it heats from the grid up to the minimum plus 0.5 °C, unless Solcast shows
   enough surplus within 90 minutes and the room is less than 1 °C below the minimum.
5. Uses minimum on/off times (10 minutes) and a 0.5 °C hysteresis to avoid rapid cycling.

Airco's in another mode than `off` or `heat` (cool, dry, auto, ...) are never touched.

> **Dry run is on by default.** The integration only reports what it would do (see the *Mode* sensors and their
> `reason` attribute) until you turn the *Dry run* switch off.

An airco that is in `heat` outside its window is switched off by the controller.

## Entities

Main device: *Enabled*, *Dry run*, *Status*, *Estimated airco power*, *Effective PV power*, *Solar surplus*.
Per airco (own device): the settings above, *Estimated power* and *Mode* (with `reason`, `action`, `setpoint`).

`Estimated airco power` is a model-based estimate (not a measurement); it is meant to be subtracted from your
house consumption or fed to an energy manager.

The model interpolates between the configured idle and maximum draw based on the room and desired temperatures:
`idle + (maximum - idle) * min(1, max(0, (desired temperature - room temperature) / 3))`.
This is an estimate, not a separate measurement, and depends on the idle and maximum values being set reasonably.

## Install

1. Push this repository to GitHub.
2. In HACS: three-dot menu → *Custom repositories* → add the repository URL, category *Integration*.
3. Install **Solar Airco**, restart Home Assistant.
4. *Settings → Devices & services → Add integration → Solar Airco*.
   - PV production: a power sensor in W.
   - House consumption: a power sensor in W. Enable *House consumption includes airco's* if the sensor includes
     configured airco's in heat mode. Their modeled heating draw is subtracted from the reading. Leave it
     disabled if the sensor already excludes them.
   - Forecast sensors: sensors with a `detailedForecast` attribute (Solcast: today and tomorrow).
5. Use *Add airco* on the integration page for each airco (climate entity, maximum power, idle power).

Repository: https://github.com/jabauwen/HA-airco-optimisation

## Development

The decision logic is in `custom_components/solar_airco/logic.py` (no Home Assistant imports):

```
python -m unittest discover -s tests -v
```
