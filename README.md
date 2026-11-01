# Solar Airco

A Home Assistant custom integration (HACS) that adjusts air-conditioner heating setpoints using the **measured
solar power left**. It does not use solar forecasts.

## How it works

Configure PV production and, optionally, house consumption. The integration calculates:

`solar capacity left = PV production - house consumption`

The *Solar capacity left* sensor reports this signed value in watts: positive means excess solar power, while
negative means the home is consuming power from the grid. If no usable house-consumption reading is available,
the configured fallback consumption is used.

For each airco, configure:

| Entity | Meaning |
|---|---|
| Day period start / end | Defines when day behavior applies; periods may cross midnight |
| Day minimum temperature | Lowest day setpoint |
| Day desired temperature | Highest day setpoint while solar power is available |
| Night temperature | Fixed setpoint outside the day period |
| Priority | Tie-breaker when aircos have the same temperature delta; 1 is increased first, larger numbers are decreased first |
| Control enabled | Enables or disables automatic control of this airco |

During the day, at each update the controller changes **at most one airco by 1 °C**:

- **Increase** only when the solar capacity left is above the *minimum solar surplus to increase* setting. The
  airco with the lowest delta (current setpoint − day minimum) goes first, up to its desired temperature.
- **Decrease** only when the grid consumption is above the *minimum grid consumption to decrease* setting. The
  airco with the highest delta goes first, down to its minimum. An airco that was increased cannot be decreased
  for the configured *decrease lock* minutes.
- Between those thresholds nothing changes. At night, the configured night temperature is applied.
- Ties on the delta are resolved by *Priority* (1 first when increasing, the highest number first when
  decreasing), and then by the order of the aircos in the list.

The update interval is configurable from 1 to 60 minutes and defaults to one minute. Aircos in modes other than
`off` or `heat` are left untouched. An airco that is off is put into `heat` when a setpoint needs to be applied.

> **Dry run is on by default.** The integration reports the intended setpoint in each airco's *Mode* sensor
> attributes (`action`, `reason`, and `setpoint`) until you turn the *Dry run* switch off.

## Entities

Main device: *Enabled*, *Dry run*, *Status*, *Solar capacity left*.
Each airco has *Day period start*, *Day period end*, *Day minimum temperature*, *Day desired temperature*,
*Night temperature*, *Priority*, a *Control enabled* switch, and a *Mode* sensor with the intended action and setpoint.
Turn off an airco's *Control enabled* switch to stop the controller managing that airco; other aircos remain
under automatic control.

## Install

1. Push this repository to GitHub.
2. In HACS: three-dot menu → *Custom repositories* → add the repository URL, category *Integration*.
3. Install **Solar Airco**, restart Home Assistant.
4. *Settings → Devices & services → Add integration → Solar Airco*.
   - PV production: a power sensor in W.
   - House consumption: a power sensor in W. If omitted or unavailable, the configured fallback is used.
   - Set the increase/decrease thresholds (W), the decrease lock (minutes) and the update interval (one minute by default).
5. Use *Add airco* on the integration page for each climate entity.

Repository: https://github.com/jabauwen/HA-airco-optimisation

## Development

The decision logic is in `custom_components/solar_airco/logic.py` (no Home Assistant imports):

```
python -m unittest discover -s tests -v
```
