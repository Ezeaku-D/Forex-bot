# Strategy Notes: DEMA Session-Overlap Strategy

**Date written:** 1 November 2026
**Status:** Rules fixed before any backtest results were seen.

## Overview

| Item | Value |
|---|---|
| Type | Trend-following: higher-timeframe bias, lower-timeframe entry |
| Pairs | EUR/USD, GBP/USD |
| Bias timeframe | 15 minutes |
| Entry timeframe | 5 minutes |
| Indicator | DEMA (period 9, close). Sessions are calculated from clock times |
| Reward-to-risk | 1:3 |
| Break-even | Stop moves to entry when the trade reaches 1:1 |
| Platform | Deriv MT5 demo account |

## Definitions

**Swing high / swing low.** A swing high is a candle whose high is the highest of the 2 candles on each side of it. A swing low is the mirror image. A swing is only confirmed after those 2 candles have formed, so the bot never uses information from the future. (Setting: `SWING_N = 2`.)

**Break of structure (BOS).** A 15-minute candle *closes* beyond the last swing in the direction of the current bias. It signals that the trend is continuing.

**Market structure shift (MSS).** A 15-minute candle *closes* beyond the last swing in the opposite direction to the current bias. It signals a possible reversal and flips the bias.

**Bias.** Bullish after a close above the last swing high, bearish after a close below the last swing low. It stays until the opposite break happens.

**Choices made for this project** (sources use these terms slightly differently):
- Closes are used, not wicks, so a brief spike through a level does not count.
- MSS and "change of character" are treated as the same event.
- Displacement (a large, fast candle) is not required. This keeps the rule simple and testable.

## Trading windows (session overlaps, UTC)

| Overlap | Hours |
|---|---|
| Sydney / Tokyo | 00:00 to 06:00 |
| Tokyo / London | 07:00 to 09:00 |
| London / New York | 13:00 to 16:00 |

Session hours: Sydney 21:00-06:00, Tokyo 00:00-09:00, London 07:00-16:00, New York 13:00-22:00. MT5 candle times are in server time, so they are converted to UTC first (`SERVER_UTC_OFFSET_HOURS` in `strategy.py`).

## Entry, stop and target

1. The 15-minute bias is bullish or bearish.
2. The 5-minute candle closes inside an overlap window.
3. **Buy:** bias is bullish, and the candle closes above the DEMA while the previous candle did not.
   **Sell:** bias is bearish, and the candle closes below the DEMA while the previous candle did not.
4. Enter at that candle's close.
5. **Stop-loss:** 0.5 pip below the candle's low (buy) or above its high (sell).
6. **Take-profit:** 3 times the distance to the stop (1:3).
7. At 1:1 profit, move the stop to the entry price (break-even).

Extra rules:
- One trade open at a time.
- At most one trade per overlap window per day.
- Trades with a stop smaller than 3 pips are skipped, because the spread would be a large part of the risk.

## Backtest assumptions
- Buys fill at the ask (price plus spread), sells at the bid.
- If one candle touches both the stop and the target, the stop is assumed to hit first.
- Results are measured in R (1R is the amount risked per trade).
- Spread is tested at 0.5, 1 and 2 pips. The average spread in the candle data is printed by `data.py`.
- Past results do not predict future results.

## Risk rules (for the live bot)
- Risk a fixed small percentage per trade (for example 1%)
- Daily loss limit and a maximum number of trades per day
- Kill switch
- No trading outside the overlap windows or when the market is closed
- Demo account only unless the teacher approves otherwise

## Why this strategy
It combines a trend filter from a higher timeframe with a precise entry, trades only during the most active hours, and has a fixed reward-to-risk ratio and a clear stop-loss.

## Expected weaknesses
- Stops on 5-minute charts are small, so spreads take a large share of each trade.
- The DEMA can give false signals when the market moves sideways.
- Market structure rules are a simplified version of how traders read charts by eye.
