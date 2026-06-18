# FileTracker Agent

基于 MCP（Model Context Protocol）的 AI 智能体，用于监控和追踪桌面上的 PDF 及 Office 文档。

## 功能

- **文件监控**：实时监听桌面文件夹的文件变化（创建、修改、移动、删除）
- **数据库查询**：SQLite 存储文件元数据，支持查询、搜索、统计
- **文件分类**：自动识别 PDF、DOC、DOCX、PPT、PPTX 类型
- **MCP 集成**：通过标准化协议与 AI 客户端（Cursor/Claude）交互

## 核心 Prompt

见 [`prompts/system_prompt.md`](prompts/system_prompt.md)

## 技术栈

| 组件 | 技术 |
|------|------|
| 文件监控 | `watchdog` |
| 数据库 | `sqlite3` |
| 文件类型识别 | `python-magic` / `mimetypes` |
| MCP 协议 | `mcp` Python SDK |
| AI 客户端 | Cursor |

## 安装

```bash
git clone https://github.com/你的用户名/filetracker-agent.git
cd filetracker-agent
python -m venv .venv

# Windows
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt