# 声屏障标准查询系统

本项目是一个本地运行的声屏障标准知识库查询系统。系统读取 `docs/` 目录下的 Excel 汇总表，把国内、国外及香港声屏障相关标准整理为可检索的条款、材料表格和 AI 助手上下文。

当前数据源：

- `docs/国内声屏障标准汇总表.xlsx`
- `docs/国外及香港声屏障标准汇总表本.xlsx`

系统默认不会访问外部数据库。普通检索完全在本地完成；AI 助手只有在 `.env` 中配置了 OpenAI 兼容接口后，才会调用大模型生成总结。

## 主要功能

- 首页快速检索：输入材料、产品、标准号或技术关键词后进入标准库结果页。
- 标准库浏览：按材料/产品分组查看 Excel 原始结构风格的技术要求表。
- 模糊检索：支持类似“岩棉的厚度”“金属单元板面密度”“Q/CR760”这类自然输入。
- 横向对比：同一材料/产品的不同标准列会按检测项目并排展示。
- AI 助手：先从本地标准库检索相关条款，再让大模型基于这些条款生成带来源的回答。
- 来源追溯：检索结果和 AI 来源会显示 `sheet!单元格`，例如 `岩棉!D3`。

## 环境要求

- Python 3.11 或更高版本
- uv

项目当前没有第三方 Python 运行依赖，Excel 读取使用 Python 标准库解析 `.xlsx` 文件。

## 安装与启动

在项目根目录运行：

```powershell
uv run python -m sound_barrier_query.web --port 8765
```

启动成功后访问：

```text
http://127.0.0.1:8765
```

也可以使用脚本入口：

```powershell
uv run sound-barrier-query --port 8765
```

常用启动参数：

```powershell
uv run python -m sound_barrier_query.web `
  --host 127.0.0.1 `
  --port 8765 `
  --workbook "docs/国内声屏障标准汇总表.xlsx" `
  --foreign-workbook "docs/国外及香港声屏障标准汇总表本.xlsx" `
  --env ".env"
```

## 页面使用

### 首页

首页适合快速开始：

- 在搜索框输入 `岩棉`、`金属单元板面密度`、`PC板透光率`、`Q/CR760` 等关键词。
- 点击快捷按钮可直接查看常用材料或指标。
- 首页的“AI助手”输入框会把问题带入 AI 助手页面并自动提问。

### 标准库

标准库页面适合查表和核对原始条款：

- 左侧导航按“国内标准”“国外及香港”等分组列出材料/产品。
- 点击材料后，右侧展示该材料对应的完整标准表。
- 搜索框支持材料 + 指标组合，例如 `岩棉的厚度`。
- 如果系统识别到材料但没有命中具体指标，会展示该材料完整表格，避免直接返回空结果。

### AI 助手

AI 助手适合让系统帮你总结、归纳和对比标准内容。推荐这样提问：

- `岩棉的国内标准和项目名称`
- `金属单元板面密度有哪些要求？`
- `PC板透光率相关标准是什么？`
- `公路声屏障防火要求等级`
- `铁路金属板的隔声量是多少`
- `帮我总结亚克力板相关技术要求`

AI 助手的工作流程：

1. 根据问题扩展领域别名，例如“铁路金属板”会优先关联到“金属单元板”，“隔音量”会关联到“计权隔声量”。
2. 在本地标准库中检索最多 12 条相关条款。
3. 如果没有检索结果，直接返回“当前标准库未检索到相关内容”，不会调用大模型。
4. 如果已配置 AI 接口，把检索条款作为上下文发送给大模型。
5. 回答中返回文字总结，并附带产品/材料、检测项目、标准、技术要求和来源单元格。

使用建议：

- 问题里尽量包含材料/产品名，例如 `岩棉`、`金属单元板`、`PC板`、`亚克力板`。
- 问题里尽量包含检测项目或指标，例如 `厚度`、`密度`、`面密度`、`透光率`、`燃烧性能`、`计权隔声量`。
- 如果只问“有什么要求”，范围会比较宽；如果加上标准范围，例如 `铁路`、`公路`、`国内标准`，结果会更聚焦。
- AI 回答只代表当前 Excel 标准库内容，不代表互联网或最新法规查询结果。

## AI 接口配置

AI 助手使用 OpenAI 兼容的 `chat/completions` 接口。项目根目录需要有 `.env` 文件，并包含：

```env
BASE_URL=https://example.com/v1
API_KEY=your-api-key
MODEL=your-model-name
```

说明：

- `BASE_URL` 可以写到 `/v1`，系统会自动拼接 `/chat/completions`。
- 如果 `BASE_URL` 已经以 `/chat/completions` 结尾，系统会直接使用。
- `API_KEY` 会以 `Authorization: Bearer ...` 方式发送。
- `MODEL` 会作为请求体中的 `model` 字段。
- `.env` 不完整时，AI 助手页面会提示 `AI接口未配置完整，请检查 .env 中 BASE_URL/API_KEY/MODEL。`

示例请求体结构：

```json
{
  "model": "your-model-name",
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": "..." }
  ]
}
```

## API 接口

服务启动后可直接调用以下接口。

### 元数据

```http
GET /api/meta
```

返回材料列表、标准列表、条款数量、材料分组和 AI 配置状态。

### 模糊检索

```http
GET /api/fuzzy-search?q=岩棉的厚度
```

适合前端主搜索。可能返回材料表格，也可能返回条款列表。

### 条款检索

```http
GET /api/search?mode=keyword&q=面密度
GET /api/search?mode=standard&q=Q/CR760
GET /api/search?mode=product&q=岩棉
```

`mode` 可选：

- `keyword`：按材料、产品、项目、标准、技术要求全文关键词检索。
- `standard`：按标准名称或标准号检索。
- `product`：按产品/材料检索。

### 材料表

```http
GET /api/material-table?q=岩棉
```

返回指定材料/产品的表格结构，包括基础列、标准列和行数据。

### 本地检索版助手

```http
GET /api/assistant?q=岩棉密度有什么要求
```

只做本地检索总结，不调用大模型。

### AI 聊天助手

```http
POST /api/chat
Content-Type: application/json

{
  "message": "金属单元板面密度有哪些要求？"
}
```

返回字段包括：

- `answer`：AI 生成的回答或错误提示。
- `sources`：本次回答使用的来源条款。
- `error`：可选，常见值包括 `empty_message`、`config_missing`、`llm_failed`。

## 数据更新

更新标准库时，直接替换或编辑 `docs/` 目录下的 Excel 文件即可。系统启动时会重新读取工作簿：

- 国内标准默认按 `国内标准` 分组。
- 国外及香港标准默认按 `国外及香港` 分组。
- 工作表名会作为材料/产品导航名称。
- 表头中需要包含 `检测项目` 或 `项目名称`，系统才会把该工作表识别为有效标准表。

## 测试

只运行与当前查询系统相关的测试：

```powershell
uv run python -m unittest tests.test_query_engine -v
```

## 项目结构

```text
docs/                                   标准 Excel 数据源
src/sound_barrier_query/
  aliases.py                            领域别名和问题扩展
  assistant.py                          本地检索助手与 RAG 提示词
  config.py                             .env 配置读取
  llm.py                                OpenAI 兼容 chat/completions 客户端
  models.py                             标准条款和表格数据模型
  search.py                             检索、模糊匹配和材料表生成
  web.py                                HTTP 服务和 API 路由
  xlsx_loader.py                        Excel 解析
  static/                               前端页面、样式和交互脚本
tests/test_query_engine.py              查询、加载、Web API 和 AI 助手测试
```
