"""SQLite 数据库操作 - 只追踪 PDF 和 Office 文档"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from config import DATABASE_PATH


class Database:
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def _init_db(self):
        """初始化数据库表结构"""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    file_name TEXT NOT NULL,
                    file_extension TEXT,
                    category TEXT,
                    file_size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP,
                    last_modified TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    current_location TEXT,
                    is_moved INTEGER DEFAULT 0,
                    original_path TEXT,
                    metadata TEXT
                );
                
                CREATE TABLE IF NOT EXISTS file_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER,
                    event_type TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    process_name TEXT,
                    process_id INTEGER,
                    old_path TEXT,
                    new_path TEXT,
                    details TEXT,
                    FOREIGN KEY (file_id) REFERENCES files(id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_files_path ON files(file_path);
                CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);
                CREATE INDEX IF NOT EXISTS idx_files_extension ON files(file_extension);
                CREATE INDEX IF NOT EXISTS idx_events_file_id ON file_events(file_id);
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON file_events(timestamp);
            """)
    
    def add_or_update_file(self, file_path: str, file_size: int = None,
                          metadata: Dict = None) -> int:
        """添加或更新文件记录，返回 file_id"""
        path = Path(file_path)
        ext = path.suffix.lower()
        
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT id, file_path FROM files WHERE file_path = ?",
                (str(path),)
            )
            existing = cursor.fetchone()
            
            if existing:
                conn.execute("""
                    UPDATE files 
                    SET last_accessed = CURRENT_TIMESTAMP,
                        access_count = access_count + 1,
                        file_size = COALESCE(?, file_size),
                        metadata = COALESCE(?, metadata)
                    WHERE id = ?
                """, (file_size, json.dumps(metadata) if metadata else None, existing["id"]))
                return existing["id"]
            else:
                cursor = conn.execute("""
                    INSERT INTO files (file_path, file_name, file_extension, 
                                     file_size, metadata)
                    VALUES (?, ?, ?, ?, ?)
                """, (str(path), path.name, ext, file_size,
                      json.dumps(metadata) if metadata else None))
                return cursor.lastrowid
    
    def record_event(self, file_id: int, event_type: str,
                     process_name: str = None, process_id: int = None,
                     old_path: str = None, new_path: str = None,
                     details: str = None):
        """记录文件事件"""
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO file_events 
                (file_id, event_type, process_name, process_id, old_path, new_path, details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (file_id, event_type, process_name, process_id, 
                  old_path, new_path, details))
    
    def update_file_location(self, file_id: int, new_path: str):
        """更新文件位置"""
        with self._connect() as conn:
            old_path = conn.execute(
                "SELECT file_path FROM files WHERE id = ?", (file_id,)
            ).fetchone()["file_path"]
            
            conn.execute("""
                UPDATE files 
                SET file_path = ?, current_location = ?, 
                    is_moved = 1, original_path = COALESCE(original_path, ?)
                WHERE id = ?
            """, (new_path, new_path, old_path, file_id))
    
    def set_file_category(self, file_id: int, category: str):
        """设置文件分类"""
        with self._connect() as conn:
            conn.execute(
                "UPDATE files SET category = ? WHERE id = ?",
                (category, file_id)
            )
    
    def get_file_by_path(self, file_path: str) -> Optional[Dict]:
        """根据路径获取文件信息"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM files WHERE file_path = ?",
                (str(Path(file_path)),)
            ).fetchone()
            return dict(row) if row else None
    
    def get_files_by_category(self, category: str) -> List[Dict]:
        """按分类获取文件"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE category = ? ORDER BY last_accessed DESC",
                (category,)
            ).fetchall()
            return [dict(r) for r in rows]
    
    def get_files_by_extension(self, extension: str) -> List[Dict]:
        """按扩展名获取文件"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM files WHERE file_extension = ? ORDER BY last_accessed DESC",
                (extension,)
            ).fetchall()
            return [dict(r) for r in rows]
    
    def get_recent_events(self, limit: int = 50) -> List[Dict]:
        """获取最近的事件"""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT fe.*, f.file_name, f.category, f.file_path
                FROM file_events fe
                JOIN files f ON fe.file_id = f.id
                ORDER BY fe.timestamp DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
    
    def get_file_history(self, file_path: str) -> List[Dict]:
        """获取单个文件的完整历史"""
        with self._connect() as conn:
            file_row = conn.execute(
                "SELECT id FROM files WHERE file_path = ? OR original_path = ?",
                (file_path, file_path)
            ).fetchone()
            
            if not file_row:
                return []
            
            rows = conn.execute("""
                SELECT * FROM file_events 
                WHERE file_id = ? 
                ORDER BY timestamp ASC
            """, (file_row["id"],)).fetchall()
            return [dict(r) for r in rows]
    
    def search_files(self, keyword: str) -> List[Dict]:
        """搜索文件"""
        with self._connect() as conn:
            pattern = f"%{keyword}%"
            rows = conn.execute("""
                SELECT * FROM files 
                WHERE file_name LIKE ? OR category LIKE ? OR file_path LIKE ?
                ORDER BY last_accessed DESC
            """, (pattern, pattern, pattern)).fetchall()
            return [dict(r) for r in rows]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) as count FROM files").fetchone()["count"]
            
            extension_counts = conn.execute("""
                SELECT file_extension, COUNT(*) as count 
                FROM files 
                WHERE file_extension IS NOT NULL
                GROUP BY file_extension
            """).fetchall()
            
            category_counts = conn.execute("""
                SELECT category, COUNT(*) as count 
                FROM files 
                WHERE category IS NOT NULL
                GROUP BY category
            """).fetchall()
            
            recent_opens = conn.execute("""
                SELECT COUNT(*) as count FROM file_events 
                WHERE event_type = 'opened' 
                AND timestamp > datetime('now', '-24 hours')
            """).fetchone()["count"]
            
            return {
                "total_files": total,
                "extension_breakdown": {r["file_extension"]: r["count"] for r in extension_counts},
                "category_breakdown": {r["category"]: r["count"] for r in category_counts},
                "recent_opens_24h": recent_opens,
            }