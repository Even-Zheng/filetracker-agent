"""文件类型识别与分类"""

import mimetypes
from pathlib import Path
from typing import Optional

try:
    import magic
    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False

from config import FILE_CATEGORIES


class FileClassifier:
    def __init__(self):
        mimetypes.init()
    
    def get_extension(self, file_path: str) -> str:
        """获取文件扩展名"""
        return Path(file_path).suffix.lower()
    
    def get_mime_type(self, file_path: str) -> Optional[str]:
        """获取 MIME 类型"""
        if HAS_MAGIC:
            try:
                return magic.from_file(file_path, mime=True)
            except Exception:
                pass
        return mimetypes.guess_type(file_path)[0]
    
    def classify_by_extension(self, file_path: str) -> str:
        """根据扩展名分类"""
        ext = self.get_extension(file_path)
        
        for category, extensions in FILE_CATEGORIES.items():
            if ext in extensions:
                return category
        
        mime = self.get_mime_type(file_path)
        if mime:
            mime_main = mime.split('/')[0]
            mime_map = {
                'image': 'image',
                'video': 'video',
                'audio': 'audio',
                'text': 'document',
                'application': 'data',
            }
            if mime_main in mime_map:
                return mime_map[mime_main]
        
        return "other"
    
    def classify(self, file_path: str) -> dict:
        """完整分类信息"""
        path = Path(file_path)
        category = self.classify_by_extension(file_path)
        mime = self.get_mime_type(file_path)
        
        return {
            "category": category,
            "extension": path.suffix.lower(),
            "mime_type": mime,
            "is_hidden": path.name.startswith('.'),
        }