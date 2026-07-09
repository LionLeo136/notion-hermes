"""
Hermes Agent API client — sends prompts and streams SSE responses to stdout.
"""

import json
import logging
import sys
from typing import Optional, Generator

import requests

logger = logging.getLogger(__name__)

# ANSI escape codes
GRAY = "\033[90m"
RESET = "\033[0m"
TOOL_COLOR = "\033[36m"  # cyan for tool calls


class HermesClient:
    def __init__(self, api_url: str, api_key: str, model: str = "hermes-agent"):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = 600  # 10 minutes for long tasks

    def send_prompt(self, prompt: str) -> bool:
        """
        Send a prompt to Hermes, stream the response to stdout.
        Returns True on success, False on error.
        """
        chat_url = f"{self.api_url}/v1/chat/completions"

        body = {
            "model": self.model,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        print(f"\n{'─' * 60}")
        print(f"🚀 Sending to Hermes ({self.model})...")
        print(f"{'─' * 60}\n")

        try:
            resp = requests.post(
                chat_url,
                json=body,
                headers=headers,
                stream=True,
                timeout=self.timeout,
            )
            resp.raise_for_status()

            current_event: Optional[str] = None
            in_thinking = False

            for line in resp.iter_lines(decode_unicode=True):
                if line is None:
                    continue

                # SSE event line
                if line.startswith("event: "):
                    current_event = line[7:].strip()
                    continue

                # SSE data line
                if line.startswith("data: "):
                    data_str = line[6:]

                    # Done signal
                    if data_str.strip() == "[DONE]":
                        if in_thinking:
                            print(RESET, end="")
                            in_thinking = False
                        print(f"\n{'─' * 60}")
                        print("✅ Hermes completed.")
                        print(f"{'─' * 60}\n")
                        sys.stdout.flush()
                        return True

                    # Handle tool progress event
                    if current_event == "hermes.tool.progress":
                        self._print_tool_progress(data_str)
                        current_event = None
                        continue

                    # Handle content delta
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    self._print_delta(data, in_thinking)
                    current_event = None

                # Reset event context on blank line (SSE spec)
                if line.strip() == "":
                    current_event = None

            # Stream ended without [DONE]
            if in_thinking:
                print(RESET, end="")
            print(f"\n{'─' * 60}")
            print("⚠️  Hermes stream ended unexpectedly (no [DONE]).")
            print(f"{'─' * 60}\n")
            return False

        except requests.exceptions.Timeout:
            logger.error("Hermes request timed out after %ds", self.timeout)
            return False
        except requests.exceptions.RequestException as e:
            logger.error("Hermes API error: %s", e)
            return False

    def _print_tool_progress(self, data_str: str):
        """Parse and display tool progress event."""
        try:
            data = json.loads(data_str)
            tool_name = data.get("tool", data.get("name", "unknown"))
            print(f"  {TOOL_COLOR}🔧 [{tool_name}]{RESET}")
            sys.stdout.flush()
        except (json.JSONDecodeError, KeyError):
            pass

    def _print_delta(self, data: dict, in_thinking: bool) -> bool:
        """Print delta content from a choice. Returns updated in_thinking flag."""
        choices = data.get("choices", [])
        if not choices:
            return in_thinking

        delta = choices[0].get("delta", {})

        # Reasoning / thinking content (gray)
        reasoning = delta.get("reasoning_content", "")
        if reasoning:
            if not in_thinking:
                print(f"\n{GRAY}", end="")
                in_thinking = True
            print(reasoning, end="", flush=True)
            return in_thinking

        # Close thinking block if we were in one
        if in_thinking:
            print(f"{RESET}\n", end="")
            in_thinking = False

        # Regular content
        content = delta.get("content", "")
        if content:
            print(content, end="", flush=True)

        return in_thinking
