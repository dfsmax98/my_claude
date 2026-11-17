---
name: fraud-strategy-brainstorm
description: 反欺诈策略分析师思维辅助技能
---

# 反欺诈策略分析师思维辅助

## 触发条件
- 关键词: 特征衍生, 规则挖掘, 策略设计, APPLIST, 通讯录, 设备指纹
- 场景: 特征挖掘前头脑风暴, 策略上线前评估

## 核心知识库

### 标签体系
- fpd_k30: 首期逾期超30天
- if_out_30d/60d: 外诉标签
- if_in_30d/60d: 内诉标签

### 数据源特征模式
1. APPLIST: 计数/比例/标志/时间类特征
2. 通讯录: 关系网络/异常模式特征
3. 通话记录: 行为模式/关系强度特征
4. 设备信息: 三源(smy/td/bs)融合特征
5. 紧急联系人/物理地址: 关联风险特征

### 衍生原则
- 时间防穿越: 特征时间 < 样本时间
- 客群区分: 贷前/贷中, app/api, 新户/老户
- 质量门槛: IV>=0.02, PSI<=0.25, Lift>=2.0

## 调用流程
1. 解析需求(标签/数据源/场景/客群)
2. 检索现有特征字典
3. 头脑风暴新特征方向
4. 输出strategy-mining兼容配置

## 输出格式
JSON结构化建议: existing_features, new_suggestions, warnings, next_steps

## 相关Skill
- strategy-mining: 特征SQL生成
- strategy-analysis: 特征评估+报告
- table-explorer: 表结构探查
