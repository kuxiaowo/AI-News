from datetime import datetime
import json
from typing import List, Dict, Any

import requests

from tool.config import get_config
from backend.logger_setup import get_logger


class DeepseekClient:
    """DeepSeek客户端，按 deepseek_API_chat.py 的请求格式封装。

    - 读取 config.json 中的 API 地址与 app 配置
    - 读取 APIkey.json 中的 APIKEY
    - 日志记录每次请求与响应（包含原始响应体）
    - mock_mode=True 时，不发起网络请求，返回基于输入的 mock 摘要
    """

    def __init__(self, config_path: str = "./config.json", apikey_path: str = "./APIkey.json"):
        self.logger = get_logger("deepseek.client")
        cfg = get_config(config_path)
        self.url = cfg["local_api"]["deepseek_api"]
        self.app_cfg = cfg.get("app", {})
        self.mock_mode = bool(self.app_cfg.get("mock_mode", True))
        self.api_key = get_config(apikey_path).get("APIKEY", "")

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def chat(self, name: str, messages: List[Dict[str, Any]], model: str = "deepseek-chat",
             max_tokens: int = 4096, stream: bool = False) -> str:
        payload = {
            "messages": messages,
            "model": model,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        self.logger.info("[%s] Request payload: %s", name, json.dumps(payload, ensure_ascii=False))

        if self.mock_mode:
            reply = self._mock_reply(messages)
            self.logger.info("[%s] Mock reply: %s", name, reply)
            return reply

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.api_key
        }
        try:
            # 直连官方接口：headers 单独传入，body 直接是 payload
            resp = requests.post(self.url, headers=headers, json=payload, timeout=60)
            raw_text = resp.text
            self.logger.info("[%s] Raw response: %s", name, raw_text)
            resp.raise_for_status()
            data = resp.json()
            reply = data['choices'][0]['message']['content']
            self.logger.info("[%s] Parsed reply: %s", name, reply)
            return reply
        except Exception:
            self.logger.exception("DeepSeek API request failed")
            raise

    @staticmethod
    def _mock_reply(messages: List[Dict[str, Any]]) -> str:
        """根据最后一条 user 消息提取新闻条目，生成几句中文总结（用于离线测试）。"""
        user_content = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_content = m.get("content", "")
                break
        # 非严格解析，仅抓取每行的标题部分
        lines = [ln.strip(" -•\t") for ln in user_content.splitlines() if ln.strip()]
        titles = []
        for ln in lines:
            if "标题：" in ln:
                titles.append(ln.split("标题：", 1)[-1].strip())
            elif ln.startswith("[") and "]" in ln:
                titles.append(ln.split("]", 1)[-1].strip())
        if not titles:
            titles = lines[:5]

        # 生成 2-3 句自然语言总结
        sents = []
        if titles:
            lead = '、'.join(titles[:3])
            sents.append(f"今日关注：{lead}等热点。" if len(titles) > 3 else f"今日关注：{lead}。")
        if len(titles) > 3:
            more = '、'.join(titles[3:5])
            if more:
                sents.append(f"此外，{more}亦有新进展。")
        if len(titles) > 5:
            sents.append("整体看，市场与技术动向交织，产业升级持续推进。")
        return "".join(sents) if sents else "今日暂无可总结的热点。"
