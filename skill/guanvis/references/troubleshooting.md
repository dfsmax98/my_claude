## Troubleshooting（常见错误 → 修复方法）

| 错误信息 | 原因 | 修复方法 |
|---|---|---|
| `zone metric: field count N exceeds max 1` | BASIC_COLUMN/BAR/LINE 只支持 1 个 metric | 改用 GROUPED_COLUMN/MULTI_LINE（支持多 metric），或拆成多个卡片 |
| `zone row: field count N exceeds max 1` | 组合图（*_WITH_LINE）row maxCount=1 | 减少 row 字段到 1 个，或改用非组合图类型 |
| `missing required zone: metric` | 卡片没有添加 metric 字段 | 调用 `.addMetric(f("字段名"))` |
| `calcField name 'X' conflicts with dataset physical field` | calcField 与数据集字段同名 | 重命名 calcField，如加 `_calc` 后缀 |
| `Calculated field missing name` | calcField 没有指定 name | 使用 `calcField("名称", "公式")` 格式 |
| `Field 'X' not found in dataset` | 字段名拼写错误或数据集中不存在 | 检查 schema.js 中的字段名，确保完全匹配 |
| `unknown chart type 'X'` | ChartType 枚举值错误 | 使用 `ChartType.XXX` 常量，不要手写字符串 |
| `auth: ...` / `401` | Token 过期或 profile 错误 | 运行 `guancli auth status`，必要时重新 `auth login` |
| `run scripts: ...ReferenceError` | JS 脚本中引用了未定义的变量 | 检查是否使用了 `new XxxBuilder()` 而非工厂函数 `createXxx()` |
| `placeCard index out of range` | placeCard 的 cardIndex 超出已注册卡片数量 | 检查 registerCard/registerTextCard 的调用顺序和总数 |
| `page has no cards` | page.js 中没有 placeCard | 确保 page.js 中为每个已注册的卡片调用了 placeCard |
| `selector not linked to any card` | selector 没有调用 linkTo/linkToAll | 添加 `.linkToAll()` 或 `.linkTo(cardIndex)` |
| `Theme: 简约 (source=fallback, built-in simple.json)` 但用户要求别的风格 | 偏好缺失 / themeId 在环境中不存在 / sync 失败 / keywords 没命中 | `theme list` 看候选 → `theme preference --theme-id ...` 或 `--keywords ... --sync`；联网命令注意 stderr 是否有 `theme: sync failed: ...` |
| publish 后 `.applied.json` 没更新 | 本次实际用的就是 skill 自带 `simple.json`（按设计 fallback 不写 applied） | 检查 stderr 的 `theme: ... falling back ...` 警告；确保对应 `themes/<id>.json` 存在或先 `theme sync` |
| `invalid themeId "..." (...)` | themeId 不是合法的单段文件名（见 `publish-and-constraints.md` 中的约束） | 使用 `theme list` 里出现的 id；避免 `/`、`\`、`..`；或用 `theme preference --keywords` |
| `theme: keywords "..." matched no theme` | 关键词与候选 themeName 没有公共子串 | `theme list` 核对候选名字；调整 keywords，或换成 `--theme-id` |
