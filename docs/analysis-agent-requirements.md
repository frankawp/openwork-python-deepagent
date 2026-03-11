# 数据分析 Agent 需求暂存

> 本文档用于暂存“业务数据分析 Agent”需求，当前实现不满足要求，先记录需求范围与验收点，后续再落地。

## 目标与场景

### 业务场景
- 业务人员提供 CSV 数据与分析目标（如：运营活动 A/B Test 分析、贷款回款批扣效果分析等）。
- 系统需要完成分析任务与分析报告产出。
- **必须保留分析过程与分析结果**，保证可追溯与复现。

### 产出要求
- `analysis/notes.md`：过程与假设、数据理解、清洗与口径说明。
- `analysis/report.md`：中文分析报告（包含结论、指标、建议）。
- `analysis/figures/*.png`：图表产出并在报告中引用。
- `analysis/outputs/*.csv`：中间与最终结果表。
- `analysis/scripts/run_analysis.py`：可复现分析入口脚本。

## 工作区规范

建议目录结构：

```
analysis/
  inputs/        # 原始 CSV
  scripts/       # 分析脚本
  figures/       # 图表
  outputs/       # 结果表
  notes.md
  report.md
```

## Python 执行约束

**必须在 workspace 内创建虚拟环境并在其中运行**，禁止使用全局 Python。

- 创建 venv：
  - `uv venv analysis/.venv`
- 依赖记录：
  - `analysis/requirements.txt`
- 安装依赖：
  - `analysis/.venv/bin/uv pip install -r analysis/requirements.txt`
- 执行脚本：
  - `analysis/.venv/bin/python analysis/scripts/run_analysis.py`

## Agent 设计要求

### Subagent 协作
需要多个专业 subagent 协作完成任务：
- `data-intake`：数据理解、字段字典、清洗与异常检查。
- `experiment-design`：指标定义、A/B 设计与口径核对。
- `stats-testing`：显著性检验、效应量、置信区间。
- `reporting`：报告结构、图表解读、建议输出。

### Skills 机制
Skills 是全局能力扩展，不是 subagent 级别的绑定，但 subagent 任务可明确遵循指定 skill。

**需要至少一个 AB Test 领域 skill：**
- 输入字段约束（user_id、group、event_date、metric 等）。
- 标准分析步骤与统计方法。
- 输出模板与常见陷阱说明。

## 前端交互

- 需要一个“分析模式”开关，用于触发分析流程与提示词。
- Analysis 模式下提示用户上传 CSV 并描述目标。

## 测试要求

### 集成测试
- 登录、线程创建、workspace 文件读取。
- `analysis_mode=true` 下 Agent 流式接口响应正确。
- HITL 流程可中断/恢复。

### 端到端测试
- UI 选择工作区 → 上传 CSV → 开启分析模式 → 提交目标。
- 生成 `notes.md`、`report.md`、`figures` 与 `outputs`。
- 确认 Python 执行使用 venv 路径（非全局 python）。

## 未完成点/待确认

- 现有实现不满足上述约束，需重新设计落地方案。
- 依赖与运行策略可能需要进一步约束（如：大数据处理、隐私合规）。
