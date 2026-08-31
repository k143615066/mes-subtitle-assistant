#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一异常处理模块

提供标准化的异常处理、错误记录、用户消息转换等功能。
"""

import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class ErrorCategory(Enum):
    """错误分类"""
    USER_INPUT = "user_input"      # 用户输入错误
    BUSINESS = "business"          # 业务逻辑错误
    SYSTEM = "system"              # 系统错误
    EXTERNAL = "external"          # 外部服务错误
    UNKNOWN = "unknown"            # 未知错误


class AppError(Exception):
    """应用基础异常类"""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        user_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.category = category
        self.user_message = user_message or self._default_user_message()
        self.details = details or {}
        self.timestamp = datetime.now()
        super().__init__(self.message)

    def _default_user_message(self) -> str:
        messages = {
            ErrorCategory.USER_INPUT: "输入数据有误，请检查后重试",
            ErrorCategory.BUSINESS: "处理过程中遇到问题，请稍后重试",
            ErrorCategory.SYSTEM: "系统繁忙，请稍后重试",
            ErrorCategory.EXTERNAL: "外部服务暂时不可用，请稍后重试",
            ErrorCategory.UNKNOWN: "发生未知错误，请联系管理员",
        }
        return messages.get(self.category, "操作失败，请重试")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "message": self.message,
            "user_message": self.user_message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class ErrorHandler:
    """统一错误处理器"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def handle_worker_error(
        self,
        session_id: str,
        session: Dict[str, Any],
        step_name: str,
        error: Exception
    ):
        """
        处理 worker 函数中的异常（致命错误，标记为 error 状态）。

        参数:
            session_id: 会话ID
            session: 会话数据
            step_name: 处理步骤名称
            error: 异常对象
        """
        if isinstance(error, AppError):
            app_error = error
        else:
            app_error = AppError(
                message=str(error),
                category=self._classify_error(error),
                details={
                    "exception_type": type(error).__name__,
                    "traceback": traceback.format_exc(),
                },
            )

        session["status"] = "error"
        session["progress"]["message"] = app_error.user_message
        session["progress"]["logs"].append(
            f"{datetime.now().strftime('%H:%M:%S')} {step_name}失败: {app_error.user_message}"
        )

        self.logger.error(
            f"[{session_id}] {step_name}失败: {app_error.message}",
            exc_info=True,
        )

    def handle_worker_degradation(
        self,
        session_id: str,
        session: Dict[str, Any],
        step_name: str,
        error: Exception,
        fallback_status: str = "optimized",
        fallback_message: str = "AI优化遇到问题，请直接校对",
    ):
        """
        处理 worker 函数中的异常（可降级处理，不标记为 error）。

        用于 _optimize_worker 等允许降级运行的场景。

        参数:
            session_id: 会话ID
            session: 会话数据
            step_name: 处理步骤名称
            error: 异常对象
            fallback_status: 降级后的状态
            fallback_message: 降级后的用户消息
        """
        session["status"] = fallback_status
        session["ai_optimized"] = True
        session["progress"]["percent"] = 100
        session["progress"]["message"] = fallback_message
        session["progress"]["logs"].append(
            f"{datetime.now().strftime('%H:%M:%S')} {step_name}异常: {str(error)}，请直接校对"
        )
        self.logger.error(f"[{session_id}] {step_name}异常: {error}", exc_info=True)

    def handle_api_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """
        处理 API 接口中的异常。

        参数:
            error: 异常对象
            context: 上下文信息（endpoint, method 等）

        返回:
            (response_data, status_code) 元组，可直接用于 jsonify 返回
        """
        if isinstance(error, AppError):
            app_error = error
        else:
            app_error = AppError(
                message=str(error),
                category=self._classify_error(error),
                details={
                    "exception_type": type(error).__name__,
                    "context": context or {},
                },
            )

        self.logger.error(
            f"API错误: {app_error.message}",
            exc_info=True,
        )

        status_code = self._get_status_code(app_error.category)
        return {
            "success": False,
            "message": app_error.user_message,
            "error_code": app_error.category.value,
        }, status_code

    def _classify_error(self, error: Exception) -> ErrorCategory:
        error_type = type(error).__name__

        if error_type in ("ValueError", "KeyError", "TypeError"):
            return ErrorCategory.USER_INPUT

        if "timeout" in error_type.lower() or "connection" in error_type.lower():
            return ErrorCategory.EXTERNAL

        if "file" in error_type.lower() or "io" in error_type.lower():
            return ErrorCategory.SYSTEM

        return ErrorCategory.SYSTEM

    def _get_status_code(self, category: ErrorCategory) -> int:
        status_codes = {
            ErrorCategory.USER_INPUT: 400,
            ErrorCategory.BUSINESS: 422,
            ErrorCategory.SYSTEM: 500,
            ErrorCategory.EXTERNAL: 503,
            ErrorCategory.UNKNOWN: 500,
        }
        return status_codes.get(category, 500)


def create_error_handler(logger: logging.Logger) -> ErrorHandler:
    """创建错误处理器实例"""
    return ErrorHandler(logger)
