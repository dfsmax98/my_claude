---
name: lovskills
description: Use only for LovSkills control-plane workflows through the logged-in LovBrowser desktop client, including local authorization, health checks, points balance, Lov API token export, AI chat window launch, Codex/Claude setup, image/video generation, and DevTask workflows. Do not use this skill for Browser Bridge reverse-browser/OpenAI-compatible ChatGPT/Gemini calls; that belongs to lovbrowser-bridge.
---

# LovSkills

LovSkills is the LovBrowser control-plane skill. It talks to the logged-in LovBrowser desktop client through LovSkills scoped local authorization at `http://127.0.0.1:18007`; the CLI does not ask for user passwords, Web JWTs, cookies, or refresh tokens.

## Skill Boundary

- LovSkills and `lovbrowser-bridge` are mutually exclusive execution paths.
- When using this skill, do not call `lovbridge`, Browser Bridge `/api/bridge/*`, OpenAI-compatible `/v1/*` reverse-browser endpoints, or `~/.codex/lovbrowser-bridge/*`.
- Use this skill for LovBrowser user/system capabilities exposed by `/api/lovskills/*`, such as points, token export, setup, chat-window launch, and LovSkills-native AI creation.
- If a requested capability only exists through Browser Bridge, stop instead of falling back from LovSkills to Browser Bridge.

## Prerequisites

- LovBrowser desktop client must be running and signed in.
- Run `lovskills login` once per local session/machine to create a scoped local token.
- LovSkills local URL priority: `LOVSKILLS_LOCAL_URL` -> `http://127.0.0.1:18007`.
- `lovskills login` writes scoped local auth to `~/.codex/lovskills/auth.json` by default.

Do not print cookies, JWTs, refresh tokens, Authorization headers, LovBrowser Web login tokens, or Lov API token keys. `lovskills tokens list` writes Lov API token keys to a local text file and prints only the file path.

## Commands

| Command | Description | Needs Desktop Client? |
|---------|-------------|----------------------|
| `lovskills login` | Grant scoped local LovSkills access | Yes |
| `lovskills doctor` | Check LovBrowser local health and authorization | Yes |
| `lovskills points balance [--json]` | Read current user's points balance | Yes |
| `lovskills balance usd [--detail|--json]` | Read current user's Lov API USD balance | Yes |
| `lovskills tokens list [--json] [--out PATH]` | Export current user's Lov API token keys to a local text file | Yes |
| `lovskills chat accounts [--provider chatgpt|gemini|claude]` | List launchable AI chat accounts | Yes |
| `lovskills chat launch [--provider ...] [--account-key ...]` | Launch a LovBrowser AI chat window only | Yes |
| `lovskills setup codex|claude` | Configure Codex/Claude with a Lov API token | Yes |
| `lovskills image` | Create AI image-generation tasks through local LovBrowser authorization | Yes |
| `lovskills video` | Create AI video-generation tasks through local LovBrowser authorization | Yes |
| `lovskills audio` | Reserved; disabled until a LovSkills-native audio endpoint exists | Yes |
| `lovskills search` | Reserved; disabled until a LovSkills-native search endpoint exists | Yes |
| `lovskills scrape` | Reserved; disabled until a LovSkills-native scrape endpoint exists | Yes |
| `lovskills task` | Manage DevTasks (pull/start/done/claim) | No |

## Usage Examples

### Local Authorization

```bash
lovskills login
lovskills doctor
```

### Points And Tokens

```bash
lovskills points balance
lovskills points balance --json
lovskills balance usd
lovskills balance usd --detail
lovskills tokens list
lovskills tokens list --out ~/Downloads/lovskills/key.txt
```

When the user only asks for their USD balance, run `lovskills balance usd` and reply with only the available USD balance from stdout. Use `--detail` or `--json` only when they ask for quota, total, used, or machine-readable output.

When the user asks for Lov API token keys, run `lovskills tokens list`. The command exports plaintext keys to `~/Downloads/lovskills/key.txt` by default and prints only the absolute file path. Reply with that path only; never paste the file contents or token keys into chat. Use `--json` only when machine-readable metadata is requested; it still must not include plaintext keys.

### AI Chat Window

```bash
lovskills chat accounts --provider chatgpt
lovskills chat launch --provider chatgpt --account-key product:chatgpt:shared:1:2:3
```

This only launches a LovBrowser kernel chat window. Do not send prompts or read chat replies from Codex for this command.

### Codex / Claude Setup

```bash
lovskills setup codex --model gpt-5.4 --full-permissions
lovskills setup claude --model claude-sonnet-4-6
```

Setup writes long-lived local tool configuration. If more than one Lov API token is available, choose interactively in a TTY or pass `--token-id`; in non-TTY contexts, provide both `--token-id` and `--model`.

### Image Generation

```bash
lovskills image "a cat wearing a hat" --model gpt-image-2 --size 1024x1024 --resolution 1K
lovskills image "a small toy figure on a desk" --model gpt-image-2 --aspect-ratio 1:1 --resolution 1K
```

Image generation creates an AI 创作 task, returns task ID/status, and the final image appears in LovBrowser's unified AI 创作 task records after backend polling completes. It requires explicit user choices for `--model`, either `--aspect-ratio` or `--size`, and `--resolution`. If any are missing, use interactive selection only in a TTY; in non-TTY contexts, stop and ask for the missing parameters.

### Video Generation

```bash
lovskills video "a sunset over the ocean" --model seedance-2.0 --ratio 16:9 --resolution 720p --duration 5 --wait
```

Video generation creates an AI 创作 task, returns task ID/status, and the final video appears in LovBrowser's unified AI 创作 task records after backend polling completes. It requires explicit user choices for `--model`, `--aspect-ratio` or `--ratio`, `--resolution`, and `--duration`. Audio generation defaults to on; pass `--no-generate-audio` only when the user requests silent video.

### Reserved Audio / Search / Scrape

```bash
lovskills audio "生成一段温柔的钢琴曲，带一点冒险电影感"
lovskills search "LovBrowser documentation"
lovskills scrape "https://example.com/article"
```

These commands intentionally fail closed in this skill until LovSkills-native endpoints exist. Do not route them through Browser Bridge from LovSkills.

### Task Management

```bash
lovskills task pull
lovskills task start 42
lovskills task done 42 --summary "completed feature"
lovskills task claim --project-id 1
```

## Provider Selection

- Control-plane commands route through LovBrowser's local service with a scoped token from `lovskills login`.
- LovSkills does not have a Browser Bridge provider and does not use Browser Bridge token files.
- Legacy `LOVBROWSER_API_URL` / `LOVBROWSER_API_TOKEN` may still be written by `lovskills setup`, but ordinary image/video/points/token/chat commands should use local LovSkills authorization by default.

## Required Choices

- `chat launch`: if multiple accounts match, choose one interactively in a TTY or pass `--account-key`; a single account may launch automatically.
- `setup codex|claude`: if multiple Lov API tokens exist, choose one interactively in a TTY or pass `--token-id`; `--model` is required outside a TTY.
- `image` and `video`: do not rely on hidden defaults for model, frame/aspect, resolution, or duration. These values must come from the user or an interactive TTY choice.

## Installation

```bash
# Repo-local
.agents/skills/lovskills/scripts/lovskills <command>

# User-level
~/.claude/skills/lovskills/scripts/lovskills <command>
~/.codex/skills/lovskills/scripts/lovskills <command>
```
