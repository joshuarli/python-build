#!/usr/bin/env python3
"""Keep Rust-for-CPython perf climbers on their pinned model.

The climber agent definitions pin claude-sonnet-5-5 and an effort level. A
per-call `model` argument to the Agent tool would override that pin, so a
PreToolUse hook rejects it (exit status 2 returns the message to Claude).
"""

import json
import sys

event = json.load(sys.stdin)
tool_input = event.get("tool_input") or {}
if str(tool_input.get("subagent_type", "")).startswith("rust-perf-climber") and tool_input.get("model"):
    print("rust-perf-climber agents pin claude-sonnet-5-5 and their effort in the agent "
          "definition; call the Agent tool again without the model parameter.", file=sys.stderr)
    sys.exit(2)
