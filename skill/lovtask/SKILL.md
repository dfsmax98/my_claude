---
name: lovtask
description: Use when working with LovBrowser DevTasks from Codex agents, CLI, or hooks against the hosted platform, including pushing requirements, pulling tasks, starting work, completing tasks, or syncing status.
---

# LovTask

统一的 LovBrowser DevTask 工作流 skill，面向通过 LovBrowser 配置好的 Codex / Claude / CLI 环境。

这个 skill 是自包含目录，不是单独的 `SKILL.md` 文档。LovBrowser 一键配置会自动把整个 `lovtask/` 目录安装到用户级 skill 目录，并保留同目录下的 `scripts/`。

## Prerequisites

- 生产推荐方式：直接使用 LovBrowser 一键配置，它会自动写入 `LOVBROWSER_API_URL`、`LOVBROWSER_API_TOKEN`，并覆盖安装 skill。
- 生产手动方式：至少准备 `LOVBROWSER_API_URL` 与 `LOVBROWSER_API_TOKEN`，生产 API 使用 `https://lovbrowser.com/api`。
- 本地开发调试：只有明确要连接本机后端时，才把 `LOVBROWSER_API_URL` 设置为 `http://localhost:8081/api`。
- 脚本不会提供默认 API URL；必须显式配置，避免生产环境误连本地后端，或本地调试误打生产。

生产手动配置示例：

```bash
export LOVBROWSER_API_URL="https://lovbrowser.com/api"
export LOVBROWSER_API_TOKEN="your-lov-access-token"
```

本地开发调试示例：

```bash
export LOVBROWSER_API_URL="http://localhost:8081/api"
export LOVBROWSER_API_TOKEN="your-local-devtask-access-token"
```

## 生产兼容

- 通用示例默认已经完成上面的环境配置，不在每条命令里重复写本地 API。
- LovBrowser 一键配置应从当前后端解析 `LOVBROWSER_API_URL`；生产 Web 的相对 `/api` 必须解析到当前站点的生产域名。
- 工具和 skill 下载 URL 使用后端返回的相对 `/api/v1/downloads/...` 路径，由当前站点 origin 解析；不要在 skill 或脚本里硬编码本地下载地址。

## Bundled Scripts

- `scripts/lovtask-claim`
- `scripts/lovtask-push`
- `scripts/lovtask-pull`
- `scripts/lovtask-start`
- `scripts/lovtask-done`

## Workflow

### 1. 领取任务闭环

当用户说“我要领取任务”“从需求池分配一个任务”“从会议待办开始做”时，优先走 `lovtask-claim`。

如果用户没有提供明确关键词，不要停下来要求用户补关键词。默认从 DevTask 任务池随机分配一个可领取任务：

1. 先运行 `scripts/lovtask-pull --include-unassigned` 拉取我的任务与未分配任务池。
2. 只把 `plan_review`、`unassigned`、`failed` 作为候选状态，排除 `executing`、`awaiting_acceptance`、`accepted`、`cancelled`。
3. 在剩余候选任务中随机选择 1 个任务。
4. 运行 `scripts/lovtask-start <task-id> --tool codex --plan` 领取并进入计划模式。
5. 如果任务池没有可领取任务，再停止并告知用户当前没有可分配任务。

会议妙记闭环：

1. 飞书妙记内容先进入会议待办。
2. 会议待办审核后通过 tooling API 转入 DevTask。
3. `lovtask-claim` 领取 DevTask 并推进到 `executing`。
4. 用户和 Codex / Claude Code 明确需求、确认计划。
5. 执行完成后用 `lovtask-done` 回写，进入待验收。

```bash
scripts/lovtask-claim \
  --from-meeting \
  --keyword "hi.docx" \
  --project-id 1 \
  --tool codex \
  --plan
```

本地会议（`LOCAL_MEETING`）闭环示例：

```bash
# 前置：管理员在 Tauri 客户端完成录音 → 转写 → 云端同步 → 提取待办
# 待办标题/片段含关键词，例如「完成同步 API」
export LOVBROWSER_API_URL="https://lovbrowser.com/api"
export LOVBROWSER_API_TOKEN="<你的 DevTask access token>"

scripts/lovtask-claim \
  --from-meeting \
  --keyword "同步 API" \
  --project-id <研发项目 ID> \
  --tool codex \
  --plan
```

- `--from-meeting` 表示先从会议待办查询并 promote 到 DevTask。
- 会议待办来源包括飞书妙记（`MEETING_MINUTE`）与 LovBrowser 本地会议（`LOCAL_MEETING`）；`--keyword` 按标题/描述/片段匹配，不区分来源类型。
- `LOCAL_MEETING` 条目由会议宿主创建，**不依赖** `t_meeting_task_visibility`；tooling API 用 Bearer `LOVBROWSER_API_TOKEN` 鉴权（与 Web JWT 相同过滤器）。
- `--keyword` 用于筛选会议待办标题、描述或原始片段。
- 没有关键词时不要走会议待办 promote，改从 DevTask 任务池随机领取。
- `--project-id` 是转入 DevTask 时使用的项目 ID。
- `lovtask-claim` 成功后会输出 DevTask ID 和后续 `lovtask-done` 提示。
- 若任务不是代码改动，而是文档、配置、交付物等非 git 产物，完成时使用 `lovtask-done --no-git --artifact <path>`。

### 2. 推需求

```bash
scripts/lovtask-push \
  --project-id 123 \
  --title "支持 access token 推需求" \
  --description "补齐 skill / CLI / hook 协作流" \
  --criteria "A 用户可推需求" \
  --criteria "B 用户可拉取任务" \
  --assignee 1002
```

- `--assignee` 可留空，留空后进入同组未分配池
- `--criteria` 可重复传入多条验收标准
- 在 git 仓库里执行时，`lovtask-push` 会自动附带当前分支
- 如果本机已安装 `gh`，并且 `gh pr view --json url --jq .url` 能取到结果，也会自动附带当前分支对应的 PR URL
- 创建时不需要手填分支或 PR，这部分由 skill / 脚本自动补齐

#### Scope-creep relations

`lovtask-push` 支持 5 个 relation 字段，在创建子单 / 拆单 / 标记重复 / 阻塞依赖时使用，所有 id 必须为数字：

```bash
# 父子关系（orchestrator 自动给 EXTRA_TASK 衍生子单使用）
scripts/lovtask-push --project-id 123 --title "child task" --parent-id 42

# 阻塞依赖（可重复，进入 executing 时后端会软告警）
scripts/lovtask-push --project-id 123 --title "下游任务" \
  --blocked-by 10 --blocked-by 11

# 弱关联（可重复）
scripts/lovtask-push --project-id 123 --title "横向引用" --related-to 20

# 标记重复
scripts/lovtask-push --project-id 123 --title "duplicate of 30" --duplicates-of 30

# 拆单（与 --parent-id 互斥）
scripts/lovtask-push --project-id 123 --title "拆出来的子项" --split-from 5
```

注意：`--parent-id` 和 `--split-from` 互斥，同时传会以 exit 2 报错。

### 3. 拉任务

```bash
scripts/lovtask-pull --include-unassigned
```

按关键字筛选：

```bash
scripts/lovtask-pull --include-unassigned --keyword "access token"
```

### 4. 开工

```bash
scripts/lovtask-start <task-id> --tool codex --model o4-mini --plan
```

`lovtask-start` 会读取任务详情，并把任务推进到 `executing`。

### 5. 完成回写

```bash
scripts/lovtask-done <task-id> --summary "$(git log -1 --pretty=format:%s)"
```

如果已经有 PR，可补上：

```bash
scripts/lovtask-done <task-id> --pr-url "https://github.com/org/repo/pull/123"
```

非代码产物任务：

```bash
scripts/lovtask-done <task-id> \
  --no-git \
  --artifact "/Users/xuejiayao/Downloads/hi.docx" \
  --summary "已生成 hi.docx 到下载目录"
```

`--no-git` 会跳过分支和 commit 探测，`--artifact` 会追加到完成摘要中，后端仍复用现有 complete API，不新增数据库字段。

## Hook / sync-status

开发过程中如果还没完成，但需要把分支、提交、PR 或阶段状态同步到平台，用 `sync-status`。

```bash
curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LOVBROWSER_API_TOKEN" \
  -d '{
    "requirementStatus": "executing",
    "branchName": "task/21-demo",
    "commitId": "abc1234",
    "summary": "coding started"
  }' \
  "$LOVBROWSER_API_URL/v1/tooling/dev-tasks/21/sync-status"
```

Hook 示例：

```bash
scripts/lovtask-done 21 --summary "$(git log -1 --pretty=format:%s)"
```

## Install

- repo 内使用：放在 `.agents/skills/lovtask/`
- LovBrowser 一键配置会覆盖安装到 `~/.codex/skills/lovtask` 或 `~/.claude/skills/lovtask`
- 手动安装时，也必须复制或软链整个 `lovtask/` 目录，而不是只复制 `SKILL.md`
- 需要跨团队统一分发时，再把这个自包含 skill 作为 plugin 的一部分发布

## Common Patterns

- 飞书妙记待办领取：`lovtask-claim --from-meeting --keyword "hi.docx" --project-id <id> --tool codex --plan`
- 本地会议待办领取：`lovtask-claim --from-meeting --keyword "同步 API" --project-id <id> --tool codex --plan`（DevTask `source_type=LOCAL_MEETING`）
- 会议聊出需求后领取：`lovtask-claim --from-meeting --keyword "<关键词>" --project-id <id> --tool codex --plan`
- 没有关键词时随机领取任务池任务：`lovtask-pull --include-unassigned` 后随机选择 `plan_review`、`unassigned`、`failed` 候选任务，再执行 `lovtask-start <task-id> --tool codex --plan`
- A 用户提需求给 B：`lovtask-push --assignee <user-id>`
- A 用户只建池子任务：不传 `--assignee`
- B 用户想看池子任务：`lovtask-pull --include-unassigned`
- 非代码交付物完成：`lovtask-done <task-id> --no-git --artifact <path> --summary "<结果>"`

## Common Mistakes

- 只复制了 `SKILL.md`，没有把整个 `lovtask/` 目录一起安装
- 只配置了 token，没有配置 `LOVBROWSER_API_URL`
- 把本地开发 API 写进生产自动化配置，导致生产任务误连本机后端
- 在非 git 仓库目录里执行 `lovtask-done` 但没有加 `--no-git`
- 用户没给关键词时停下来要关键词，而不是从任务池随机分配
- 从会议待办领取时忘记传 `--project-id`，导致 promote 无法创建 DevTask
- `--assignee` 传了错误用户名或邮箱，导致无法解析同组用户
- 把 admin 路由和 tooling 路由混用，直接调用错接口
