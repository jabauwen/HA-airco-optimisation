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
| Controlled | Enables or disables this airco's control |

During the day, at each update, the controller raises the current setpoint by 1 °C when there is solar power left,
up to the desired temperature. When the home is consuming power, it lowers the setpoint by 1 °C, but not below
the minimum. If production matches consumption, the setpoint stays unchanged. At night, it applies the configured
night temperature.

The update interval is configurable from 1 to 60 minutes and defaults to one minute. Aircos in modes other than
`off` or `heat` are left untouched. An airco that is off is put into `heat` when a setpoint needs to be applied.

> **Dry run is on by default.** The integration reports the intended setpoint in each airco's *Mode* sensor
> attributes (`action`, `reason`, and `setpoint`) until you turn the *Dry run* switch off.

## Entities

Main device: *Enabled*, *Dry run*, *Status*, *Solar capacity left*.
Each airco has *Day period start*, *Day period end*, *Day minimum temperature*, *Day desired temperature*,
*Night temperature*, *Controlled*, and a *Mode* sensor with the intended action and setpoint.

## Install

1. Push this repository to GitHub.
2. In HACS: three-dot menu → *Custom repositories* → add the repository URL, category *Integration*.
3. Install **Solar Airco**, restart Home Assistant.
4. *Settings → Devices & services → Add integration → Solar Airco*.
   - PV production: a power sensor in W.
   - House consumption: a power sensor in W. If omitted or unavailable, the configured fallback is used.
   - Set the update interval (one minute by default).
5. Use *Add airco* on the integration page for each climate entity.

Repository: https://github.com/jabauwen/HA-airco-optimisation

## Development

The decision logic is in `custom_components/solar_airco/logic.py` (no Home Assistant imports):

```
python -m unittest discover -s tests -v
```
