#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI API客户端模块

提供统一的AI API调用接口，封装重试机制、错误处理和日志记录。
"""

import time
import logging
from typing import Dict, List, Optional, Any
import requests

logger = logging.getLogger(__name__)


class AIClient:
    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str,
        default_timeout: int = 120,
        max_retries: int = 3,
        default_temperature: float = 0.3
    ):
        self.api_key = api_key
        self.api_base = api_base.rstrip('/')
        self.model = model
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.default_temperature = default_temperature

    def _build_url(self, endpoint: str = "chat/completions") -> str:
        return f"{self.api_base}/{endpoint}"

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _build_payload(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.default_temperature,
        }
        payload.update(kwargs)
        return payload

    def call_api(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        **kwargs
    ) -> str:
        timeout = timeout if timeout is not None else self.default_timeout
        max_retries = max_retries if max_retries is not None else self.max_retries

        url = self._build_url()
        headers = self._build_headers()
        payload = self._build_payload(messages, temperature, **kwargs)

        last_exception = None

        for attempt in range(max_retries):
            try:
                logger.debug(f"AI API调用尝试 {attempt + 1}/{max_retries}")
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
                resp.raise_for_status()
                result = resp.json()

                content = result["choices"][0]["message"]["content"].strip()
                logger.debug(f"AI API调用成功，返回内容长度: {len(content)}")
                return content

            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(f"AI API调用超时（尝试 {attempt + 1}/{max_retries}）: {e}")
            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(f"AI API调用失败（尝试 {attempt + 1}/{max_retries}）: {e}")
            except (KeyError, IndexError) as e:
                last_exception = e
                logger.error(f"AI API返回数据格式错误: {e}")
                raise RuntimeError(f"AI API返回数据格式错误: {e}")

            if attempt < max_retries - 1:
                sleep_time = 2 ** attempt
                logger.debug(f"等待 {sleep_time} 秒后重试...")
                time.sleep(sleep_time)

        error_msg = f"AI API调用失败，已重试 {max_retries} 次"
        if last_exception:
            error_msg += f": {last_exception}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    def call_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.call_api(messages, temperature=temperature, **kwargs)