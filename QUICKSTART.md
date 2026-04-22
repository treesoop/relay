# Relay Quickstart

3 minutes to first capture + share.

## Prerequisites

- Claude Code installed (see https://claude.com/claude-code)
- Python 3.11+
- git

## Install

    curl -fsSL https://raw.githubusercontent.com/treesoop/relay/main/install.sh | bash

Or clone and run locally:

    git clone https://github.com/treesoop/relay.git
    cd relay && ./install.sh

Restart Claude Code. You should see `plugin:relay:relay` in `/mcp` output.

## Your first skill

Talk to Claude Code about anything you're currently debugging. When you solve it, say:

> "Capture this as a Relay skill."

Claude calls `/relay:capture` for you, proposing a name. Confirm, and the skill lands under `~/.claude/skills/mine/<name>/`.

Run `/relay:status` to see it listed.

## Sharing it

    /relay:upload <name>

This masks PII, POSTs the skill to the central commons, and updates the local sidecar with the canonical server id.

## Discovering other people's skills

    /relay:search <natural language description of your problem>

Read the top results. If one matches, use `/relay:upload` to pull it into `~/.claude/skills/downloaded/`.

After trying it:

    /relay:review <skill_id> good   # or bad / stale

## What gets uploaded

- The SKILL.md body (markdown prose)
- The `.relay.yaml` metadata (problem, attempts, solution, tools)

Bodies and failure messages are regex-masked for API keys, emails, and bearer tokens before storage. Review the masked result before confirming.

## What stays local

- Anything you capture but don't `upload`.
- Private skill corpus under `~/.claude/skills/mine/`.

## Troubleshooting

- **`/mcp` shows no `plugin:relay:relay`** — restart Claude Code after install.
- **"relay-mcp: command not found"** — add `~/.local/bin` to your PATH.
- **Upload returns 500** — central API likely restarting; retry in 30s.
