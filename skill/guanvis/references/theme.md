## 仪表板主题

`preview` / `pack` / `publish` 会自动给页面与卡片注入主题，决策顺序如下：

1. **`<dir>/themes/.preference.json`** — 用户/AI 主动写入的意图（`themeId` 优先，缺失再用 `keywords` 在 `.index.json` 上匹配；命中后 `themeId` 会被回写到 `.preference.json`）
2. **`<dir>/themes/.applied.json`** — 上一次成功 `pack`/`publish` 选用的线上主题（用于改版自动继承；本次回退到 skill 自带 `simple.json` 时**不写**该文件）
3. **skill 自带 `simple.json`** — 兜底（embed 在二进制里，**不联网、不会失败**）

AI 选择主题时不要把租户主题列表里的默认“浅色”/“深色”当作候选：这两套主题没有特殊样式。若除了“浅色”/“深色”外没有合适主题，不写主题偏好或执行 `theme preference --clear`，让解析落到 skill 内置“简约”（`simple.json`），不要为了命中而从列表里随便挑一个。

兜底覆盖的失败场景（任意一种发生都会平滑退到 simple.json，命令不会因主题问题中断）：
- 工程目录下没有 `themes/`、或 `.preference.json` 缺失
- `.preference.json` 里的 `themeId` 在租户线上 list 中不存在 / `Sync` 失败 / 当前命令本来就不联网
- `keywords` 在 `.index.json` 上没有任何命中
- `.applied.json` 引用的 `themeId` 本地快照已被删除（applied 步骤**只读本地、不再发起 sync**）

每次执行命令时 stderr 会打印决策结果。命中线上主题时形如 `Theme: <name> [<id>] (source=preference|applied)`；落到自带兜底时形如 `Theme: 简约 (source=fallback, built-in simple.json)`，特意不打印 themeId 是因为那只是 skill 与 BI 默认值对齐的实现细节，不是租户主题列表里能查到的 ID。

普通数据集图表和指标平台 MetricChart 都会应用主题视觉配置。MetricChart 只注入 `settings` 与 `meta.chartMain.props`：透视表补表格/合计样式，柱线饼等补坐标轴、图例、数据标签和主题色；不会修改 `zoneData`、`dsInfo`、`defaultView` 等查询相关字段。

### 何时主动操作

> 所有 `theme *` 子命令的 **`[dir]` 可省**，缺省为当前工作目录；下面的示例假设你已经 `cd` 到 dashboard 工程目录。

- **用户描述风格**（如"深色科技风" "蓝色简约"）：

  ```bash
  guanvis theme preference --keywords "深色 科技" --sync
  ```

  - `--keywords` 按 **空格 / 英文逗号 `,` / 中文逗号 `，`** 切分；命中分数最高者，平局取 `.index.json` 中**靠前**的条目（不区分 `themeType`）。AI 不应把默认“浅色”/“深色”作为关键词目标或手动指定的候选；命中后会把 `themeId` 写回 `.preference.json`，让 preview/pack/publish 后续都稳定指向同一主题。
  - `--sync` 写入偏好后立刻拉一次 `/api/theme-setting/list` 落盘到 `themes/<id>.json` + `.index.json` + `.sync-meta.json`，让随后的 preview/pack 在离线状态也能看到真实主题。

- **用户给出明确的 themeId**：

  ```bash
  guanvis theme preference --theme-id custom_blue
  ```

  themeId 需为单个「安全文件名」片段：`[A-Za-z0-9_-]`、长度 ≤32，且不能含 `/`、`\`、子串 `..`；否则 CLI 会拒绝，sync 也会跳过并打 stderr 警告。

- **改版（不重提风格）**：什么都不用做，`.applied.json` 会让本次 `pack`/`publish` 沿用上次主题。
- **换风格**：再跑一次 `theme preference` 即可；下一次 `pack`/`publish` 实际使用新主题时 `.applied.json` 会自动覆盖。
- **没有合适主题**：不要选择默认“浅色”/“深色”，也不要从列表里随便挑；保持无偏好或执行 `theme preference --clear`，使用内置“简约”兜底。
- **回到 skill 自带兜底**：`guanvis theme preference --clear` 会**同时**删除 `.preference.json` 和 `.applied.json`，下次 `preview`/`pack`/`publish` 必然落到内置 `simple.json`（只删 `.preference.json` 而保留 `.applied.json` 的话，解析仍会通过 applied 继承上次主题，所以 `--clear` 一并清掉）。

### 离线 vs 联网

| 命令 | 是否联网 | 说明 |
|---|---|---|
| `preview` / `pack` | **不联网** | 只读 `themes/`，缺主题文件直接退到 skill 自带 `simple.json`（不会因弱网失败） |
| `publish` | 按需 | 选定的 `themeId` 缺主题文件时调一次 list；list 失败则退到 `simple.json` + 警告，不阻塞发布 |
| `theme preference --sync` / `theme sync` | 是 | 强制刷新；网络失败仅打 warning，不会损坏既有 `themes/` 内容 |

> 想让 `preview` 看到与 `publish` 一致的主题，**先**跑 `theme preference --sync` 或 `theme sync`，再 `preview`。

### `themes/` 目录文件说明

| 文件 | 作用 | 是否入库 |
|---|---|---|
| `<themeId>.json` | 单主题快照（list 单条原文，含 `themeSettings`） | 推荐入库（diff 友好） |
| `.preference.json` | 用户/AI 偏好 | 入库 |
| `.applied.json` | 上次记录的线上主题 | 入库 |
| `.index.json` | `themeId/themeName/themeType` 索引，供 keywords 匹配 | 入库 |
| `.sync-meta.json` | `syncedAt`、条目数 | 可选 |

不要直接手改 `<themeId>.json`——每次 `sync` 会原子覆盖；要改就改 `.preference.json`。

### 排错

- `theme show` 打印当前决策（`source` / `themeId` / `themeName` / `themeType`），只读。
- `theme list` 列出 `.index.json` 中候选；`.index.json` 缺失时提示先 `sync`。
- 看到 `Theme: 简约 (source=fallback, built-in simple.json)` 但用户期望非简约：检查 `.preference.json` 是否写好、对应 `themes/<id>.json` 是否存在；如果是 keywords 路径，跑 `theme list` 看候选名字是否真的包含关键词；联网命令还要看 stderr 是否打印了 `theme: sync failed: ...`。
- 看到 `multi-subdir project under <root> contains per-subdir themes/ in [...]`：你在多子目录工程的**根目录**直接跑了 preview/pack/publish，但子目录里有自己的 `themes/`。按提示 `cd` 进每个子目录单独执行；或如果不想用各子目录的主题，删除子目录下的 `themes/` 后再回到根目录运行。

## 设计规则

`preview` / `pack` / `publish` 会自动应用内置设计规则。需要覆盖默认视觉规则时，在工程目录新建 `design-rule.json`，不要手改 `themes/<themeId>.json`。

`design-rule.json` 只用于两类配置：

- `componentDefaults`：卡片静态默认规则，例如 `SINGLE_VALUE` 单指标卡、`KPI_CARD` 对比指标卡的默认布局与样式。指标卡/对比指标卡布局类配置只通过这里统一配置，不放进 `themePatch`，也不提供单张卡片 props 透出。
- `themePatch`：仅用于主题已开放的主题配置，例如页面背景、标题样式、主题色等；不要把指标卡布局类配置放进 `themePatch`。

数据格式不放在 `design-rule.json` 里，数值/百分比格式由字段类型与图表区域规则自动处理。

示例：

```json
{
  "schemaVer": 1,
  "componentDefaults": {
    "SINGLE_VALUE": {
      "singleValueSetting": {
        "alignment": "left",
        "fontStyle": {
          "size": 28
        }
      }
    },
    "KPI_CARD": {
      "secondKpiSetting": {
        "valueAlign": "right"
      }
    }
  },
  "themePatch": {
    "cardTitle": {
      "style": {
        "fontSize": 14
      }
    }
  }
}
```

非法字段会被忽略并打印 warning，不要依赖未支持的配置项。
