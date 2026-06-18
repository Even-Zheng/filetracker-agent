"""FileTracker Agent 配置 - 只监控桌面办公文件"""

import os
from pathlib import Path

# 只监控桌面
WATCH_DIRECTORIES = [
    r"C:\Users\你的用户名\Desktop",
]

# 只追踪这些文件类型
TARGET_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx"
}

# 数据库路径
DATABASE_PATH = Path(__file__).parent / "data" / "filetracker.db"

# 文件类型分类映射
FILE_CATEGORIES = {
    "document": [".pdf", ".doc", ".docx"],
    "presentation": [".ppt", ".pptx"],
}

# 忽略的文件模式
IGNORE_PATTERNS = [
    r"^\.",
    r"~$",
    r"\.tmp$",
    r"\.temp$",
    r"Thumbs\.db$",
    r"\.DS_Store$",
]