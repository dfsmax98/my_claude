---
name: lovbrowser-bridge
description: Use only when Codex should call LovBrowser's local Browser Bridge reverse browser/OpenAI-compatible API to generate text, images, or audio through logged-in ChatGPT/Gemini web accounts, including saving generated media to the local machine. Do not use this skill for LovSkills control-plane workflows such as points, token export, setup, or chat-window launch.
---

# LovBrowser Bridge

Use this skill when the user wants to borrow LovBrowser's local Browser Bridge as an OpenAI-compatible reverse browser API.

## Skill Boundary

- `lovbrowser-bridge` and LovSkills are mutually exclusive execution paths.
- When using this skill, do not call `lovskills`, `/api/lovskills/*`, or `~/.codex/lovskills/*`.
- Use this skill only for Browser Bridge reverse-browser model operations such as `lovbridge models`, `chat`, `image`, and `audio`.
- If the user asks for LovBrowser control-plane data or setup, stop instead of falling back from Browser Bridge to LovSkills.

## Prerequisites

- LovBrowser desktop client must be running.
- The user must be signed in to the LovBrowser desktop client. On supported clients, login automatically installs this skill, writes the local Bridge token file, starts the default ChatGPT/Gemini Bridge kernels, and scans ready models.
- A token is discovered only from the saved local Bridge token file written by LovBrowser or from `lovbridge token bind <token>`. `LOVBROWSER_API_TOKEN` is intentionally ignored so Lov API tokens from LovSkills setup cannot be reused as Bridge credentials.

Do not print tokens, cookies, Authorization headers, or Chromium command-line secrets.

## CLI

Run the bundled script from this repository:

```bash
.agents/skills/lovbrowser-bridge/scripts/lovbridge doctor
.agents/skills/lovbrowser-bridge/scripts/lovbridge token bind "<token>"
.agents/skills/lovbrowser-bridge/scripts/lovbridge accounts --provider chatgpt
.agents/skills/lovbrowser-bridge/scripts/lovbridge accounts --provider chatgpt --raw
.agents/skills/lovbrowser-bridge/scripts/lovbridge models --provider chatgpt
.agents/skills/lovbrowser-bridge/scripts/lovbridge models --provider gemini --capability image
.agents/skills/lovbrowser-bridge/scripts/lovbridge models --provider gemini --capability audio
.agents/skills/lovbrowser-bridge/scripts/lovbridge ensure --provider gemini --capability image --account-key "<account-key>"
.agents/skills/lovbrowser-bridge/scripts/lovbridge ensure --provider gemini --capability audio --account-key "<account-key>"
.agents/skills/lovbrowser-bridge/scripts/lovbridge chat --provider chatgpt --account-key "<account-key>" --model "<model>" "你好，介绍一下自己"
.agents/skills/lovbrowser-bridge/scripts/lovbridge image --provider gemini --account-key "<account-key>" --model "<model>" "生成一张白底黑字测试图"
.agents/skills/lovbrowser-bridge/scripts/lovbridge audio --model gemini-lyria-3 --out ./audio "生成一段温柔的钢琴曲"
```

If the skill is installed into Codex's personal skill directory, the equivalent path is `~/.codex/skills/lovbrowser-bridge/scripts/lovbridge`.

Defaults:

- Base URL priority: `LOVBROWSER_BRIDGE_URL` → `http://127.0.0.1:18007`.
- Image output directory: `~/Downloads/lovbrowser-bridge`, override with `--out`.
- Audio output directory: `~/Downloads/lovbrowser-bridge`, override with `--out`.
- If `--account-key` is omitted, the CLI uses the first account for the provider and prints the chosen label to stderr.
- If a ready model exists, `chat`/`image`/`audio` uses it directly and does not start another kernel.
- If no ready model exists, `chat`/`image`/`audio` runs `ensure` with the selected account, then re-checks models.
- If `--model` is omitted, the CLI uses the first ready Bridge model for the provider/capability and prints it to stderr.
- Image generation prints a Markdown image line first, then prints `file: <absolute-path>` for debugging.
- `accounts` prints readable labels by default, such as `ChatGPT:shared <ai-account>`. Use `accounts --raw` when you need the original `accountKey`.

## Workflow

1. Run `lovbridge doctor` first when diagnosing setup.
2. Determine capability from the task: text uses `chat`; image generation uses `image`; music/audio generation uses `audio`.
3. For image generation, ask the user whether they want automatic prompt optimization before running `lovbridge image`.
4. If the user wants optimization, use the `lovbrowser-image-prompt` skill to produce a Chinese optimized image prompt. Show the optimized prompt to the user and wait for confirmation or edits before continuing.
5. Bridge-side prompt optimization is local agent prompt composition. It does not consume LovBrowser points and must not call LovSkills control-plane APIs.
6. First run `lovbridge models --capability chat|image|audio`, optionally with `--provider chatgpt|gemini` if the user specified a provider.
7. If ready models are returned, use the first matching model by default unless the user requested a specific one.
8. If no ready model is returned, run `lovbridge ensure --provider chatgpt|gemini --capability chat|image|audio`; supported LovBrowser clients reuse the client login context and default AI account.
9. If ensure succeeds but no ready model appears, ask the user to open LovBrowser and visit Browser Bridge status; do not blindly call `/v1/*`.
10. `lovbridge token bind <token>` is only for old clients or local debugging when LovBrowser did not write the saved token file.
11. Image generation downloads the returned `/v1/assets/<asset_id>` URL to a local file. Relay the emitted Markdown image line (`![Generated image](...)`) in your final answer so Codex renders the image; use the `file:` line only for debugging.
12. Audio generation saves the returned `filePath` MP3 to `--out`; if `filePath` is absent, it falls back to URL or base64 audio data.

## Common Failures

- `No token is configured`: ask the user to open/sign in to LovBrowser desktop once so it can auto-install skills and write the token file. Use `lovbridge token bind <token>` only as a fallback for old clients/debugging.
- `bridge_login_context_missing`: ask the user to sign in to the LovBrowser desktop client, then retry the CLI command.
- `bridge_account_not_found`: ask the user to run `lovbridge accounts --provider chatgpt|gemini` and choose one of the listed account keys.
- `bridge_binding_not_ready`: LovBrowser started a kernel but did not scan a ready binding; ask the user to retry after the provider page finishes loading.
- No ready models from `lovbridge models`: treat this as the kernel not being ready; choose an AI account and run `lovbridge ensure`.
