"""
FileTracker MCP 服务器 - 监控 C D 盘 PDF 和 Office 文档
"""

import asyncio
import json
import os
import logging
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server

from database import Database
from file_classifier import FileClassifier
from file_watcher import FileWatcher


# 设置日志写入文件，而不是打印到控制台
logging.basicConfig(
    filename='filetracker.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


db = Database()
classifier = FileClassifier()
watcher = FileWatcher()

app = Server("filetracker")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有可用工具"""
    return [
        Tool(
            name="get_all_documents",
            description="获取所有 PDF 和 Office 文档列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "extension": {
                        "type": "string",
                        "description": "按扩展名筛选",
                        "enum": [".pdf", ".doc", ".docx", ".ppt", ".pptx"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回数量限制",
                        "default": 50
                    }
                }
            }
        ),
        Tool(
            name="get_recent_files",
            description="获取最近访问的文件",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "返回数量",
                        "default": 20
                    }
                }
            }
        ),
        Tool(
            name="search_files",
            description="按关键词搜索文件",
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词"
                    }
                },
                "required": ["keyword"]
            }
        ),
        Tool(
            name="get_file_history",
            description="获取文件的访问历史",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件完整路径"
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="get_file_stats",
            description="获取文件统计",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_files_by_location",
            description="查找指定位置的文件",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "目录路径"
                    }
                },
                "required": ["directory"]
            }
        ),
        Tool(
            name="classify_file",
            description="分析文件信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件路径"
                    }
                },
                "required": ["file_path"]
            }
        ),
        Tool(
            name="start_watching",
            description="启动监控",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="scan_directory",
            description="扫描指定目录",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "目录路径"
                    }
                },
                "required": ["directory"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """处理工具调用"""

    if name == "get_all_documents":
        extension = arguments.get("extension")
        limit = arguments.get("limit", 50)

        with db._connect() as conn:
            if extension:
                rows = conn.execute("""
                    SELECT * FROM files WHERE file_extension = ?
                    ORDER BY last_accessed DESC LIMIT ?
                """, (extension, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM files
                    ORDER BY last_accessed DESC LIMIT ?
                """, (limit,)).fetchall()
            files = [dict(r) for r in rows]

        result = {
            "count": len(files),
            "filter": extension,
            "files": [
                {
                    "name": f["file_name"],
                    "path": f["file_path"],
                    "extension": f["file_extension"],
                    "category": f["category"],
                    "size": f["file_size"],
                    "last_accessed": f["last_accessed"],
                    "access_count": f["access_count"],
                }
                for f in files
            ]
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "get_recent_files":
        limit = arguments.get("limit", 20)

        with db._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM files
                ORDER BY last_accessed DESC LIMIT ?
            """, (limit,)).fetchall()
            files = [dict(r) for r in rows]

        result = {
            "count": len(files),
            "files": [
                {
                    "name": f["file_name"],
                    "path": f["file_path"],
                    "extension": f["file_extension"],
                    "category": f["category"],
                    "last_accessed": f["last_accessed"],
                }
                for f in files
            ]
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "search_files":
        keyword = arguments["keyword"]
        files = db.search_files(keyword)

        result = {
            "keyword": keyword,
            "matches": len(files),
            "files": [
                {
                    "name": f["file_name"],
                    "path": f["file_path"],
                    "extension": f["file_extension"],
                    "category": f["category"],
                    "last_accessed": f["last_accessed"],
                    "current_location": f["current_location"] or f["file_path"],
                }
                for f in files
            ]
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "get_file_history":
        file_path = arguments["file_path"]
        history = db.get_file_history(file_path)
        file_info = db.get_file_by_path(file_path)

        result = {
            "file": {
                "name": file_info["file_name"] if file_info else Path(file_path).name,
                "current_path": file_info["file_path"] if file_info else file_path,
                "extension": file_info["file_extension"] if file_info else None,
                "category": file_info["category"] if file_info else None,
            },
            "event_count": len(history),
            "history": [
                {
                    "event_type": h["event_type"],
                    "timestamp": h["timestamp"],
                    "process": h["process_name"],
                    "old_path": h["old_path"],
                    "new_path": h["new_path"],
                    "details": h["details"],
                }
                for h in history
            ]
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "get_file_stats":
        stats = db.get_stats()
        return [TextContent(type="text", text=json.dumps(stats, ensure_ascii=False, indent=2))]

    elif name == "get_files_by_location":
        directory = arguments["directory"]
        with db._connect() as conn:
            pattern = f"{directory}%"
            rows = conn.execute("""
                SELECT * FROM files
                WHERE file_path LIKE ? OR current_location LIKE ?
                ORDER BY last_accessed DESC
            """, (pattern, pattern)).fetchall()
            files = [dict(r) for r in rows]

        result = {
            "directory": directory,
            "file_count": len(files),
            "files": [
                {
                    "name": f["file_name"],
                    "path": f["current_location"] or f["file_path"],
                    "extension": f["file_extension"],
                    "category": f["category"],
                    "last_accessed": f["last_accessed"],
                }
                for f in files
            ]
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "classify_file":
        file_path = arguments["file_path"]
        classification = classifier.classify(file_path)
        file_info = db.get_file_by_path(file_path)

        result = {
            "file_path": file_path,
            "classification": classification,
            "tracked": file_info is not None,
            "access_count": file_info["access_count"] if file_info else 0,
            "last_accessed": file_info["last_accessed"] if file_info else None,
        }
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    elif name == "start_watching":
        if not watcher.is_running:
            watcher.scan_existing()
            watcher.start()
            return [TextContent(type="text", text=json.dumps({
                "status": "started",
                "message": "文件监控已启动",
                "watched_directories": watcher.directories
            }, ensure_ascii=False))]
        else:
            return [TextContent(type="text", text=json.dumps({
                "status": "already_running",
                "message": "文件监控已在运行中"
            }, ensure_ascii=False))]

    elif name == "scan_directory":
        directory = arguments["directory"]
        if directory not in watcher.directories:
            watcher.directories.append(directory)

        count = 0
        for root, _, files in os.walk(directory):
            for filename in files:
                filepath = os.path.join(root, filename)
                ext = Path(filepath).suffix.lower()
                if ext not in {".pdf", ".doc", ".docx", ".ppt", ".pptx"}:
                    continue

                classification = classifier.classify(filepath)
                file_id = db.add_or_update_file(
                    filepath,
                    file_size=os.path.getsize(filepath) if os.path.exists(filepath) else None,
                    metadata=classification
                )
                db.set_file_category(file_id, classification["category"])
                count += 1

        return [TextContent(type="text", text=json.dumps({
            "directory": directory,
            "files_indexed": count,
            "message": f"成功索引 {count} 个文件"
        }, ensure_ascii=False))]

    else:
        return [TextContent(type="text", text=f"未知工具: {name}")]


def initialize():
    """初始化"""
    logger.info("FileTracker Agent 初始化中...")
    logger.info("监控范围: C盘 D盘 所有 PDF / DOC / DOCX / PPT / PPTX")
    watcher.scan_existing()
    watcher.start()
    logger.info("初始化完成，等待 MCP 客户端连接...")


if __name__ == "__main__":
    initialize()

    async def main():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )

    asyncio.run(main())