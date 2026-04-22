"""
logging_config.py — 结构化日志配置

使用 Python 标准 logging 模块配置结构化输出。

使用方式：
    from core.logging_config import setup_logging
    setup_logging()  # 应用启动时调用一次
"""
import logging
import logging.config
import os
import sys


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "detailed": {
            "format": "%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d]: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": "storage/logs/app.log",
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5,
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "": {  # root
            "level": "INFO",
            "handlers": ["console", "file"],
        },
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
        "agent": {
            "level": "DEBUG",
            "handlers": ["console", "file"],
            "propagate": False,
        },
        "memory.rag": {
            "level": "DEBUG",
            "handlers": ["console", "file"],
            "propagate": False,
        },
    },
}


def setup_logging():
    """初始化日志配置（应在应用启动时调用一次）"""
    os.makedirs("storage/logs", exist_ok=True)
    logging.config.dictConfig(LOGGING_CONFIG)
    logging.getLogger(__name__).info("日志系统初始化完成")
