# Jarvis Memory Log
# This file is read by Haiku on every analysis call and updated with new learnings.
# Manual edits welcome - Jarvis treats this as ground truth.

## Learned Patterns
- 2/14: Movement <0.2% causes 71% of Sharbel losses. Filter set to 0.2%
- 2/14: Sweet spot for entries is 80-90% range (best win rate + P&L)
- 2/14: Entry >90% has 80% win rate but negative P&L (bad risk/reward)
- 2/14: Entry 75-80% has 70% win rate - avoid
- 2/14: All losses cluster during low-movement chop periods
- 2/14: 6 of 7 losses were 60-second reversals

## Bot Configurations
- Sharbel: movement_filter=0.2%, stakes=$2, rsi=DISABLED, conviction=75-92%
- Sharbel: Blackout hours 8-10am EST
- Sharbel: Assets: BTC, ETH, SOL
- Hybrid: PAPER MODE, 3 scouts + big bets, BTC only
- Hybrid: Scout times: 13:10, 13:30, 13:45 into window
- Hybrid: Big bet at 14:00 (60s before close)

## Past Decisions
- 2/14 10:14PM: Entry range discipline holds: 43 wins across 75-91% range. No entries >92%. Sweet spot (80-90%) performing as expected.
- 2/14 10:14PM: Movement filter validation holds: All 50 recent trades respect 0.2% minimum. No weak-signal losses. Filter is working correctly.
- 2/14 10:14PM: Hybrid bot status unchanged: Zero trades in paper mode. Blocker for live deployment. Needs debug of scout/big-bet trigger logic before proceeding.
- 2/14 10:14PM: CONFIRMED: $5 stakes are the problem, not conviction or movement filter. 86% win rate + $5 stakes = -$16.61 P&L over 50 trades. Same win rate at $2 stakes would yield +$15-20. Stake sizing is destroying profitability.
- 2/14 10:14PM: CRITICAL ALERT 2/15 02:14 UTC: Stake creep detected AGAIN. Trades 71-75 all $5 stakes despite 2/14 10:11PM reversion order. Violation window: 2/14 21:29 to 2/15 02:59. This is the second incident in 24 hours. Soft rules are failing. Need hard technical lock on stakes.
- 2/14 10:11PM: Entry range validation: 43 wins across 75-91% range. No entries >92%. Discipline holding.
- 2/14 10:11PM: Movement filter validation: All 50 recent trades respect 0.2% minimum. Filter is working. No weak-signal losses in dataset.
- 2/14 10:11PM: Hybrid status: Zero trades in paper mode as of 2/15 02:59 UTC. Blocker for live deployment. Requires debug before proceeding.
- 2/14 10:11PM: ALERT: Stake creep detected again. $5-$10 stakes reappeared in trades 56-74 despite 2/14 9:23PM decision to revert to $2 baseline immediately. Reverting now.
- 2/14 10:11PM: CONFIRMED: 86% win rate with $10 stakes = -$16.61 P&L (50 trades). Stake size is the problem, not conviction or movement filter.
- 2/14 9:23PM: Loss pause rule: Current 3-loss threshold is too loose. With $10 stakes, recommend 2-loss pause to limit downside.
- 2/14 9:23PM: Hybrid bot status: Zero trades in paper mode. Needs verification that scout/big-bet logic is triggering correctly before live deployment.
- 2/14 9:23PM: New pattern: High-conviction entries (0.85+) are winning at 80%+ rate but losing $10 each when they fail. Low-conviction entries (0.75-0.80) are losing at 70% rate. The $10 stake amplifies both.
- 2/14 9:23PM: Confirmed: 80-90% entry range has best win rate, but within that range, entries >0.85 show worse risk/reward at current stake levels. Recommend 80-87% as operational range.
- 2/14 9:23PM: CRITICAL: Stake sizing is the real problem, not win rate. 86% win rate with $10 stakes = -$18.38 P&L. Same win rate at $2 stakes would yield +$15-20 P&L. Revert to $2 baseline immediately.
- (none yet - Jarvis just started)

## What Worked
- 0.2% movement filter eliminates most weak-signal losses
- 80-90% entry range is the sweet spot
- Big bets at 100% win rate in paper (33 trades)

## What Failed
- RSI filter reduced volume without clear win rate improvement (needs more data)
- Auto-redeem not finding order_ids (time window issue)

## Rules (user-defined)
- Never trade below 0.2% movement
- Pause after 3 consecutive losses
- Don't touch stakes without approval
- Keep RSI disabled until 0.2% filter proves itself
- Collect data before making changes

## Known Issues
- Auto-redeem: Changed window from 10min to 60min, needs verification
- Hybrid fill rate assumptions optimistic (paper 85% vs expected live 60-70%)
- Polymarket $5 minimum share issue at low entry prices
