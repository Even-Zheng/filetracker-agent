"""实时文件系统监控 - 只监控 C D 盘 PDF 和 Office 文档"""

import os
import re
import logging
import psutil
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from database import Database
from file_classifier import FileClassifier
from config import IGNORE_PATTERNS, WATCH_DIRECTORIES, TARGET_EXTENSIONS


# 设置日志
logger = logging.getLogger(__name__)


def get_process_for_file(file_path: str) -> tuple:
    """尝试获取访问文件的进程信息"""
    try:
        for proc in psutil.process_iter(['pid', 'name', 'open_files']):
            try:
                if proc.info['open_files']:
                    for f in proc.info['open_files']:
                        if f.path == file_path:
                            return proc.info['name'], proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        pass
    return None, None


def should_ignore(path: str) -> bool:
    """检查是否应忽略该文件"""
    name = Path(path).name
    
    for pattern in IGNORE_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    
    ext = Path(path).suffix.lower()
    if ext not in TARGET_EXTENSIONS:
        return True
    
    return False


class FileEventHandler(FileSystemEventHandler):
    def __init__(self, db: Database, classifier: FileClassifier,
                 on_event: Optional[Callable] = None):
        self.db = db
        self.classifier = classifier
        self.on_event = on_event
        super().__init__()
    
    def _get_file_size(self, path: str) -> Optional[int]:
        try:
            return os.path.getsize(path)
        except OSError:
            return None
    
    def _handle_event(self, event: FileSystemEvent, event_type: str,
                      old_path: str = None, new_path: str = None):
        """统一处理文件事件"""
        path = new_path or event.src_path
        
        if should_ignore(path):
            return
        
        if event.is_directory:
            return
        
        proc_name, proc_id = None, None
        if event_type in ('opened', 'created'):
            proc_name, proc_id = get_process_for_file(path)
        
        classification = self.classifier.classify(path)
        category = classification["category"]
        
        file_id = self.db.add_or_update_file(
            path, 
            file_size=self._get_file_size(path),
            metadata=classification
        )
        
        self.db.set_file_category(file_id, category)
        
        self.db.record_event(
            file_id=file_id,
            event_type=event_type,
            process_name=proc_name,
            process_id=proc_id,
            old_path=old_path,
            new_path=new_path,
            details=f"进程: {proc_name}" if proc_name else None
        )
        
        if event_type == 'moved' and old_path:
            old_file = self.db.get_file_by_path(old_path)
            if old_file:
                self.db.update_file_location(old_file['id'], new_path)
        
        if self.on_event:
            self.on_event({
                "event_type": event_type,
                "file_path": path,
                "category": category,
                "process": proc_name,
                "timestamp": datetime.now().isoformat(),
            })
    
    def on_created(self, event):
        self._handle_event(event, 'created')
    
    def on_modified(self, event):
        self._handle_event(event, 'modified')
    
    def on_moved(self, event):
        self._handle_event(event, 'moved', 
                          old_path=event.src_path, 
                          new_path=event.dest_path)
    
    def on_deleted(self, event):
        path = event.src_path
        if should_ignore(path):
            return
        file_info = self.db.get_file_by_path(path)
        if file_info:
            self.db.record_event(
                file_id=file_info['id'],
                event_type='deleted',
                details=f"File deleted: {path}"
            )


class FileWatcher:
    """文件监控管理器"""
    
    def __init__(self, directories: list = None):
        self.directories = directories or WATCH_DIRECTORIES
        self.db = Database()
        self.classifier = FileClassifier()
        self.observer = Observer()
        self.handler = None
        self._running = False
    
    def start(self, on_event: Optional[Callable] = None):
        """启动监控"""
        self.handler = FileEventHandler(self.db, self.classifier, on_event)
        
        for directory in self.directories:
            if os.path.exists(directory):
                self.observer.schedule(self.handler, directory, recursive=True)
                logger.info(f"监控目录: {directory}")
            else:
                logger.warning(f"目录不存在，跳过: {directory}")
        
        self.observer.start()
        self._running = True
        logger.info("文件监控已启动...")
    
    def stop(self):
        """停止监控"""
        self.observer.stop()
        self.observer.join()
        self._running = False
        logger.info("文件监控已停止")
    
    def scan_existing(self):
        """扫描现有文件建立初始索引"""
        logger.info("正在扫描 C D 盘所有 PDF 和 Office 文档...")
        count = 0
        for directory in self.directories:
            if not os.path.exists(directory):
                logger.warning(f"跳过不存在的目录: {directory}")
                continue
            logger.info(f"扫描目录: {directory}")
            for root, _, files in os.walk(directory):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    
                    ext = Path(filepath).suffix.lower()
                    if ext not in TARGET_EXTENSIONS:
                        continue
                    
                    if should_ignore(filepath):
                        continue
                    
                    classification = self.classifier.classify(filepath)
                    file_id = self.db.add_or_update_file(
                        filepath,
                        file_size=self._get_file_size(filepath),
                        metadata=classification
                    )
                    self.db.set_file_category(file_id, classification["category"])
                    count += 1
                    if count % 100 == 0:
                        logger.info(f"已找到 {count} 个目标文件...")
        logger.info(f"已索引 {count} 个 PDF/Office 文件")
        return count
    
    def _get_file_size(self, path: str) -> Optional[int]:
        try:
            return os.path.getsize(path)
        except OSError:
            return None
    
    @property
    def is_running(self):
        return self._running