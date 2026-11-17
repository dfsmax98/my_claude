## 在线同步机制

`publish` 和 `upload` 命令通过 BI 的 transfer API 直接将资源包上传到目标系统：

- **接口**：`POST /api/manual/template/transfer`（标准 multipart/form-data，表单字段名 `new-file`）
- **认证**：随底层 `guancli fetch` 使用 `Cookie: uIdToken=...`
- **关键 header**：`raw-backend-response: TRUE`（绕过前端代理层，直达后端）
- **ID 策略**：`needIdMapping=false`，保持资源 ID 不变。同 ID 资源会被覆盖更新。为避免部分 BI 版本在导入前探测 Card 时缓存"找不到相关卡片"，`guanvis publish/upload` 的在线覆盖检查只探测目标环境已有 Page ID；检测到同 ID Page 时默认拒绝上传，只有明确加 `--allow-overwrite` 才允许覆盖。加 `--allow-overwrite` 后，CLI 会先调用资源包导出为冲突 Page 生成备份记录，并等待导出成功；备份失败或超时则中止上传。Card/Selector ID 不做在线探测；如果资源包不包含 Page，则不会执行在线覆盖检查。更新已有仪表板时应按新版本策略生成新的 Page/Card/Selector ID。
- **通用性**：不需要目标系统开启"一键迁移"开关，所有客户环境可用
- **异步执行**：上传成功后返回 `taskId`，后端异步完成导入

`upload` 只是上传器，不是自定义资源包制作入口。默认只允许上传由 `guanvis pack` 原样生成的 ZIP；禁止手工生成、解包修改或重打包资源包。

若用户要求批量重绑资源、迁移已有页面或复用线上页面结构，先说明风险并确认方案；不要直接修改 ZIP 内部文件后上传。

修改或重新发布已存在的仪表板资源时，默认按“新版本仪表板”处理：先从目标 BI 线上环境同步最新资源状态，再基于同步后的内容生成新的 Page/Card/Selector ID，并给仪表板名称追加版本号后发布。用户可能已经在 BI 上手工改过页面布局、卡片配置、筛选器或说明文本；如果只按本地旧文件 `publish`，同 ID 资源会被覆盖，导致线上改动丢失。只有用户明确要求覆盖原资源时，才允许保留原 ID 并同 ID 发布。

## 认证与 CLI 集成

- 所有 API 调用通过底层 CLI 代理执行
- 认证由底层 CLI 负责：guancli 使用 `guancli auth use <profile>` 设置的活跃环境；guancli-lite 使用 `GUANCLI_BASE_URL`/`GUANCLI_TOKEN` 环境变量
- CLI 二进制路径通过 `GUANCLI_PATH` 环境变量指定，或自动在 PATH 中查找 `guancli-lite`/`guancli`

## 硬约束

- `schema.js` 由 `init` 命令自动生成，不允许 AI 或人工修改。
- card 脚本必须调用 `registerCard(card.build())`（目录模式）或返回 `card.build()`（单文件模式）。
- metric chart 脚本必须调用 `registerMetricChart(card.build())`。
- text card 脚本必须调用 `registerTextCard(textCard.build())`。
- image card 脚本必须调用 `registerImageCard(imageCard.build())`。
- custom chart 脚本必须调用 `registerCustomChart(chart.build())`。
- selector 脚本必须调用 `registerSelector(selector.build())`。
- `fdId` 和 `dsId` 必须匹配目标 BI 系统的真实值（通过 schema.js 保证）。
- card 文件名建议 `card_NN_xxx.js` 控制执行顺序。
- selector 文件名建议 `selector_NN_xxx.js`，在 card 之后执行。
- page 文件必须命名为 `page.js`。
- 筛选器的 `linkTo(cardIndex)` 中 cardIndex 基于过滤后的可联动目标序列（0-based）：普通图表和 MetricChart 按注册/布局顺序，文本/图片等不可联动资源不占序号，杜邦子图追加在末尾。
- 资源包 ZIP 是派生产物，不是可编辑源文件；不要手工编辑或重打包 ZIP。
- **文件访问边界**：只允许访问以下路径，不要主动探索或读取用户未明确授权的其他目录：
  - 当前工作目录（`-d` 指定的目录或 cwd）
  - `guancli` / `guanvis` CLI 工具的输出
  - 用户在对话中明确提到或授权的路径
  - 禁止为了"查找参考代码""寻找类似实现"而主动扫描用户机器上的其他项目目录，这会引起安全顾虑。

### ID 管理

所有 Card、Selector 和 Page **必须**调用 `.setId(id)` 设置显式 ID。未设置 ID 会在 JS 校验和 Go 校验两层报错，阻止生成。

- `.setId(id)` 的 ID **必须**为严格 24 位字母数字字符串（正则：`^[a-zA-Z0-9]{24}$`），与后端 `RandUtil.uuid` 格式一致。若生成或手填的 ID 以数字开头，建议重新生成一组，避免 BI 前端某些路径把 ID 拼成 CSS selector（如 `#5bef...`）时触发 `querySelector` 语法错误。
- **生成 ID**：先运行 `guanvis genid <数量>` 生成足够的 ID，在编写脚本时直接填入每个 card/selector/page 的 `.setId()` 调用中。
- **线上更新默认策略**：已发布过或线上正在使用的仪表板，后续修改默认生成新的 Page/Card/Selector ID，并给 Page 名称追加版本号后发布，保留旧版本不覆盖。
- **覆盖前检查**：发布前可先运行 `guanvis publish <dir> --dry-run` 或 `guanvis upload <zip> --dry-run`，只构建/解析资源并列出将被覆盖的线上 Page，不提交 transfer 任务。
- **显式覆盖场景**：只有用户明确要求覆盖原仪表板时，才保持 `.setId()` 不变，并在 `publish/upload` 时加 `--allow-overwrite` 允许同 ID Page 覆盖；多次同 ID 发布会覆盖资源（因为 transfer API 的 `needIdMapping=false`），其中 Card/Selector ID 不做在线覆盖检查。覆盖前备份只创建资源迁移导出记录并打印 packageId，不自动下载资源包；需要回滚时，用户应到 BI 资源迁移导出记录中下载该资源包，再手动导入覆盖回去。
