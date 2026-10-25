"""
LLM Provider interface - supports Gemini, OpenAI, Anthropic.
Uses whichever API key is available. Temperature 0, caching by input hash.
"""
import hashlib
import json
import os
import base64
from typing import Any, Dict, List, Optional, Tuple
from .usage import UsageLogger


# Cost per 1M tokens (from docs/assumptions.md)
COST_TABLE = {
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
}


def get_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    costs = COST_TABLE.get(model, {"input": 0.50, "output": 1.50})
    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000


class LLMProvider:
    """Thin LLM provider interface with caching."""

    def __init__(self, usage_logger: UsageLogger):
        self.usage = usage_logger
        self.cache: Dict[str, Any] = {}
        self.provider, self.model, self.client = self._init_provider()

    def _init_provider(self) -> Tuple[str, str, Any]:
        """Initialize the best available provider."""
        # Load env.local if present
        for env_file in ["env.local", ".env.local", ".env"]:
            if os.path.exists(env_file):
                try:
                    with open(env_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                k = k.strip()
                                v = v.strip().strip('"').strip("'")
                                if k not in os.environ or not os.environ[k]:
                                    os.environ[k] = v
                except Exception:
                    pass

        # Try Gemini first (cheapest + vision)
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                return "google", "gemini-2.5-flash-lite", client
            except Exception as e:
                pass

        # Try OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                return "openai", "gpt-4o-mini", client
            except ImportError:
                pass

        # Try Anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                return "anthropic", "claude-3-5-haiku-20241022", client
            except ImportError:
                pass

        raise RuntimeError(
            "No LLM provider available. Set GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY."
        )

    def _cache_key(self, messages: List[dict], tools: Optional[List] = None) -> str:
        """Generate a cache key from the input."""
        content = json.dumps(messages, sort_keys=True)
        if tools:
            content += json.dumps(tools, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def chat(self, messages: List[dict], tools: Optional[List[dict]] = None,
             purpose: str = "", case_id: str = "") -> dict:
        """Send a chat completion request. Returns parsed response."""
        cache_key = self._cache_key(messages, tools)
        if cache_key in self.cache:
            return self.cache[cache_key]

        if self.provider == "google":
            result = self._chat_gemini(messages, tools)
        elif self.provider == "openai":
            result = self._chat_openai(messages, tools)
        elif self.provider == "anthropic":
            result = self._chat_anthropic(messages, tools)
        else:
            raise RuntimeError(f"Unknown provider: {self.provider}")

        # Log usage
        self.usage.log_call(
            model=self.model,
            provider=self.provider,
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            cost=get_cost(self.model, result.get("input_tokens", 0), result.get("output_tokens", 0)),
            purpose=purpose,
            case_id=case_id,
        )

        self.cache[cache_key] = result
        return result

    def _chat_gemini(self, messages: List[dict], tools: Optional[List[dict]] = None) -> dict:
        """Chat using Google Gemini API."""
        from google import genai
        from google.genai import types

        # Convert messages to Gemini format
        contents = []
        system_instruction = None
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content
                continue

            # Handle image content
            parts = []
            if isinstance(content, str):
                parts.append(types.Part.from_text(text=content))
            elif isinstance(content, list):
                for item in content:
                    if item.get("type") == "text":
                        parts.append(types.Part.from_text(text=item["text"]))
                    elif item.get("type") == "image_url":
                        # Handle base64 images
                        url = item["image_url"]["url"]
                        if url.startswith("data:"):
                            mime, b64 = url.split(",", 1)
                            mime_type = mime.split(":")[1].split(";")[0]
                            parts.append(types.Part.from_bytes(
                                data=base64.b64decode(b64),
                                mime_type=mime_type
                            ))

            gemini_role = "model" if role == "assistant" else "user"
            contents.append(types.Content(role=gemini_role, parts=parts))

        config = types.GenerateContentConfig(
            temperature=0,
            system_instruction=system_instruction,
        )

        # Add tools if provided
        if tools:
            tool_declarations = []
            for tool in tools:
                func = tool.get("function", {})
                tool_declarations.append(types.Tool(
                    function_declarations=[types.FunctionDeclaration(
                        name=func["name"],
                        description=func.get("description", ""),
                        parameters=func.get("parameters"),
                    )]
                ))
            config.tools = tool_declarations

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        # Extract response
        text = ""
        tool_calls = []
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.text:
                    text += part.text
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    tool_calls.append({
                        "name": fc.name,
                        "arguments": dict(fc.args) if fc.args else {},
                    })

        input_tokens = getattr(response, 'usage_metadata', None)
        output_tokens_count = 0
        input_tokens_count = 0
        if input_tokens:
            input_tokens_count = getattr(input_tokens, 'prompt_token_count', 0) or 0
            output_tokens_count = getattr(input_tokens, 'candidates_token_count', 0) or 0

        return {
            "text": text,
            "tool_calls": tool_calls,
            "input_tokens": input_tokens_count,
            "output_tokens": output_tokens_count,
        }

    def _chat_openai(self, messages: List[dict], tools: Optional[List[dict]] = None) -> dict:
        """Chat using OpenAI API."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t["function"]} for t in tools]

        response = self.client.chat.completions.create(**kwargs)

        text = response.choices[0].message.content or ""
        tool_calls = []
        if response.choices[0].message.tool_calls:
            for tc in response.choices[0].message.tool_calls:
                tool_calls.append({
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments) if tc.function.arguments else {},
                })

        return {
            "text": text,
            "tool_calls": tool_calls,
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
        }

    def _chat_anthropic(self, messages: List[dict], tools: Optional[List[dict]] = None) -> dict:
        """Chat using Anthropic API."""
        system = ""
        filtered_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                filtered_messages.append(msg)

        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": filtered_messages,
            "temperature": 0,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [{"name": t["function"]["name"],
                                "description": t["function"].get("description", ""),
                                "input_schema": t["function"].get("parameters", {})}
                               for t in tools]

        response = self.client.messages.create(**kwargs)

        text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "name": block.name,
                    "arguments": block.input,
                })

        return {
            "text": text,
            "tool_calls": tool_calls,
            "input_tokens": response.usage.input_tokens if response.usage else 0,
            "output_tokens": response.usage.output_tokens if response.usage else 0,
        }
