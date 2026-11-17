# 实时语音听写 + LLM 润色 PoC(复刻 Typeless)

复刻 Typeless 的原生功能,全本地可控。**三个模块,各一个热键**:

| 热键(默认) | 模块 | 做什么 |
|---|---|---|
| `Ctrl+Alt+D` | 口述 | 转写 → 润色成稿 → 敲到光标处 |
| `Ctrl+Alt+T` | 翻译 | 转写 → 翻成目标语言 → 敲到光标处 |
| `Ctrl+Alt+A` | 问答/改写 | **按"是否选中文字"自动切换**(见下) |

**问答/改写模块(第 3 个)的智能判断**:
- **光标有选中文字** → 你口述的话当作**指令**,对选中内容做改写/翻译/精简/解释等,结果**替换选中**。(对标 Typeless 的 SelectedText 能力)
- **没有选中** → 你口述的话当作**问题**,AI 直接作答并敲到光标处。

```
全局热键 → 麦克风 → 本地流式 ASR(FunASR,CPU)→ 边说边出字
       → LLM(润色/翻译/问答/改写)→ 自动敲到当前光标处
```

**数据不出内网**:ASR 本地跑,LLM 走你们自己的网关(`llmapi.lovbrowser.com`)。
反欺诈研判作为扩展保留(`--fraud`),后续本地化再深化。

## 目录结构

| 文件 | 作用 |
|---|---|
| `config.py` | 读 `.env` / 环境变量配置 |
| `audio_capture.py` | 麦克风采集 + 能量检测 |
| `asr_engine.py` | FunASR 流式识别封装 |
| `llm_client.py` | 可插拔 LLM 客户端:`format_text`(润色)/ `analyze_fraud`(研判) |
| `text_injector.py` | 把成稿敲到光标处(剪贴板粘贴,中文友好) |
| `prompts.py` | 润色 / 研判 两套提示词 |
| `pipeline.py` | 听写主链路 + 热键控制 |
| `main.py` | 入口(多种模式) |

## 安装

```bash
cd voice_llm_poc
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

## 配置

```bash
cp .env.example .env
# 编辑 .env:填 LLM_API_KEY,按需改 LLM_MODEL、HOTKEY 等
```

## 新增体验(对标 Typeless)

- **屏幕下方浮窗**:按热键后屏幕底部中央出现小浮窗——录音时是**动态音量条**(随音量跳动),后台处理时显示**"思考中"**,完成/空闲自动消失。开关见 `.env` 的 `SHOW_FLOATING_BAR`。(浮窗是独立置顶桌面小窗,所有程序之上都能看到)
- **置信度/降噪门控**:没说话或只有杂音时,**不再瞎返回**,而是提示**"没听清,请再说一遍"**。判据:一句话里有效语音时长 < `MIN_VOICED_MS` 或转写字数 < `MIN_TEXT_LEN` 就拦截,不调 LLM。
- **语言**:当前以中文为主(`LANG=zh`,paraformer-zh 流式模型)。

## 三种界面形态(任选)

| 启动方式 | 形态 |
|---|---|
| `python main.py` | 控制台(日志在终端) |
| `python main.py --tray` | 桌面托盘图标 + 状态灯 |
| `python main.py --web` | 浏览器仪表盘(状态/音量条/实时转写/历史)|

三种形态都带**屏幕浮窗**和**全局热键**。

## 快捷启动(Windows,双击即用)

免敲命令,提供批处理:

| 文件 | 用途 |
|---|---|
| `安装依赖.bat` | **第一次用**:双击装好所有依赖(PyTorch CPU 版 + 其余) |
| `启动语音助手.vbs` | **托盘版日常用**:双击静默启动,托盘图标出现,无黑窗 |
| `启动网页版.bat` | **网页版**:启动后自动开浏览器仪表盘 |
| `启动-调试.bat` | **排错用**:带控制台窗口启动,能看到日志和报错 |

**建议**:第一次先双击 `安装依赖.bat`,再用 `启动-调试.bat` 跑一次确认没问题(首次会下模型),之后日常用 `启动语音助手.vbs`。

**开机自启(可选)**:按 `Win+R` 输入 `shell:startup` 打开启动文件夹,把 `启动语音助手.vbs` 的快捷方式放进去即可。

> 注:`.vbs` 静默启动看不到报错;若双击后托盘没出现,改用 `启动-调试.bat` 看原因。
> 若依赖装在独立虚拟环境,把它建在本目录 `venv\` 下,启动器会自动识别。

## 运行(命令行方式,等价)

```bash
python main.py --check                          # 1. 查配置和依赖
python main.py --dictate  "嗯那个明天十点开会对下数据啊"   # 2a. 验证网关:口述润色
python main.py --translate "明天上午十点开会"             # 2b. 验证网关:翻译
python main.py --ask      "北京到上海高铁要多久"          # 2c. 验证网关:问答
python main.py --no-llm --print                 # 3. 验证 ASR(首次下载模型,只打印转写)
python main.py                                  # 4a. 控制台模式:三个热键各管一个模块
python main.py --tray                           # 4b. 托盘模式(推荐):常驻托盘图标 + 状态灯
```

**托盘模式(`--tray`)**:启动后右下角出现话筒图标,随状态变色——
灰=空闲、红=录音中、橙=生成中;右键菜单可看三个热键、打开配置、退出。
功能和控制台模式一样,只是常驻后台更像 Typeless。

**实际使用**:把光标放到任意输入框 →
- 口述:按 `Ctrl+Alt+D`,说话,再按一次 → 润色成稿敲入;
- 翻译:按 `Ctrl+Alt+T`,说中文,再按 → 译文敲入;
- 问答/改写:按 `Ctrl+Alt+A` →
  - 若**先选中了一段文字**:说"改得正式些/翻译这段/精简一下" → 结果替换选中;
  - 若**没选中**:说一个问题 → AI 回答敲入。

## 与 Typeless 的对应关系

| Typeless 原生 | 本 PoC |
|---|---|
| 听写(Transcribe) | 口述模块 `format_text` |
| 翻译(Translate) | 翻译模块 `translate_text` |
| 问 AI(Ask)| 问答模块 `answer_question` |
| 选中文字改写(SelectedText)| 问答模块按选中自动切 `rewrite_selection` |
| Opus 编码上传云端 ASR | 本地 FunASR 流式(数据不出内网) |
| 云端 LLM | 你们网关 LLM(OpenAI 兼容) |
| input-helper 敲字 / 读选中 | `text_injector`(剪贴板粘贴 / 模拟 Ctrl+C 抓选中) |
| 全局热键 | pynput GlobalHotKeys |

## 调参 / 已知简化

- 换模型/热键/翻译目标语言/注入方式 → 改 `.env`。
- 各模块提示词 → 改 `prompts.py`。
- 注入中文失败 → 用 `INJECT_METHOD=paste`(默认);某些应用禁用 Ctrl+V 时改 `key`。
- 选中改写:抓选中靠模拟 Ctrl+C,极少数应用可能不支持;结果替换选中,误操作可 Ctrl+Z 撤销。
- pynput 全局热键在部分系统需以管理员运行终端。
- 未做说话人分离/读屏上下文感知(留给后续本地化与声纹融合)。
- LLM 非流式;要"边说边出"可后续加 SSE。
