---
type: summary
slug: trading-agent-demo
vault_id: test-vault
---

# Self-Improving Trading Agent on Hermes

This page introduces three concepts: the Hermes API (a tool for accessing
real-time market data), backtesting (a methodology for evaluating trading
strategies on historical data), and reinforcement learning (a paradigm where
agents learn from reward signals).

The agent uses the Hermes API to fetch L1 order books, then runs backtesting
on the past 30 days of data, refining its strategy via reinforcement
learning.
