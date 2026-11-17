# Skill 文件夹

本文件夹用于存放和管理 Claude Code 的 Skill（技能）。

## 什么是 Skill？

Skill 是 Claude Code 的扩展功能，类似于插件，可以增强 Claude 的能力，使其能够执行特定的任务或提供专业领域的帮助。

## 已安装的 Skill

| Skill | 来源 | 用途 |
|-------|------|------|
| **skill-creator** | anthropics/skills | 创建/编辑/优化 Skill，跑 eval 测试与 benchmark |
| **guanvis** | 本地（观远 BI 专项） | 生成观远 BI / Guandata 的 Card、筛选器、Page 并发布 |
| **sample-feature-join-sql** | 本地（反欺诈专项） | 样本表 × 特征宽表关联聚合 SQL 生成 |
| **guizang-ppt** | guizang | 横向翻页网页 PPT（单 HTML，含 WebGL 背景）|
| **huashu-design** | 花叔Design（MIT） | HTML 高保真原型、幻灯片、动画、可视化 |
| **ppt-master** | hugohe3/ppt-master（AGPL-3.0） | PPTX ⇄ SVG 转换、图像生成、配音等 PPT 全流程 |
| **cosyncing** | 本地 | 把生成的文件/产物投递到手机端 |
| **lov-model** | 本地 | 会话内快速切换模型的清单助手 |
| **lovbrowser-bridge** / **lovskills** / **lovtask** | 本地（LovBrowser） | LovBrowser 浏览器桥接 / 控制面 / DevTask |
| **reverse-engineer-anything** | 本地 | 逆向分析各类目标的方法论 |
| **lgbm-modeling-cn** | 本地 | 基于 LightGBM 的中文二分类风控建模全流程 |

> 这些是 `~/.claude/skills/` 下生效的 Skill 副本，本目录作备份 / 版本管理。
> 公司内部业务知识库、含客户 PII 的探查结果、真人音频/声纹数据均未上传。

_最后同步：2026-11-16_

## 如何安装 Skill？

### 方法1：使用 npx（推荐）

```bash
# 安装官方 Skill 集合
npx skills add anthropics/skills

# 安装特定的 Skill
npx skills add <skill-repository>
```

### 方法2：手动安装

1. 从以下来源下载 Skill：
   - [skills.sh](https://skills.sh) - Vercel 官方 Skill 商店
   - [ClawHub](https://clawhub.ai) - OpenClaw Skill 集合
   - [GitHub](https://github.com/anthropics/skills) - Anthropic 官方 Skill

2. 将 Skill 文件夹复制到本目录

3. 确保 Skill 配置文件正确

### 方法3：通过 Claude Code 安装

在 Claude Code 对话中直接请求安装：
```
请帮我安装这个 Skill，项目地址为: https://github.com/anthropics/skills/tree/main/skills/skill-creator
```

## 推荐的 Skill

### 基础 Skill
- **skill-creator** - 从任何工作流创建 Skill
- **find-skills** - 通过对话发现和安装 Skill
- **superpowers** - 完整的开发工作流框架

### 文档处理
- **pdf-processor** - PDF 文档处理
- **excel-helper** - Excel 数据分析
- **word-doc** - Word 文档处理

### 开发工具
- **frontend-design** - 专业 UI/UX 设计指导
- **react-helper** - React 开发助手
- **python-dev** - Python 开发工具

## 文件夹结构

```
skill/
├── README.md                    # 本文件
├── skill-creator/               # Skill 创建工具
├── pdf-processor/               # PDF 处理 Skill
├── excel-helper/                # Excel 处理 Skill
└── ...                         # 其他 Skill
```

## 管理 Skill

### 查看已安装的 Skill
```bash
npx skills list
```

### 更新 Skill
```bash
npx skills update
```

### 移除 Skill
```bash
npx skills remove <skill-name>
```

## 注意事项

1. 每个 Skill 应有自己的子文件夹
2. 确保 Skill 与当前 Claude Code 版本兼容
3. 定期更新 Skill 以获得最新功能
4. 如果遇到问题，查看 Skill 自带的文档

## 问题反馈

如果在安装或使用 Skill 时遇到问题：
1. 查看对应 Skill 的 GitHub Issues
2. 在 Claude Code 社区寻求帮助
3. 检查 Claude Code 版本是否支持该 Skill

## 更新日志

- **2026-04-02**：创建 Skill 文件夹和说明文档

---

> 提示：Skill 的安装和管理可能需要 Node.js 环境。确保已安装 Node.js v16+。