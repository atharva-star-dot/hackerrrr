"""
Usage tracking module - logs model calls, tokens, and costs.
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from threading import Lock


@dataclass
class ModelCall:
    model: str
    provider: str
    timestamp: float
    input_tokens: int
    output_tokens: int
    cost: float
    purpose: str  # what the call was for
    case_id: str = ""


class UsageLogger:
    """Thread-safe usage logger for model API calls."""

    def __init__(self):
        self.calls: List[ModelCall] = []
        self._lock = Lock()

    def log_call(self, model: str, provider: str, input_tokens: int, output_tokens: int,
                 cost: float, purpose: str, case_id: str = ""):
        with self._lock:
            self.calls.append(ModelCall(
                model=model,
                provider=provider,
                timestamp=time.time(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                purpose=purpose,
                case_id=case_id,
            ))

    def get_summary(self) -> dict:
        """Get a summary of all usage."""
        with self._lock:
            total_calls = len(self.calls)
            total_input = sum(c.input_tokens for c in self.calls)
            total_output = sum(c.output_tokens for c in self.calls)
            total_cost = sum(c.cost for c in self.calls)
            total_tokens = total_input + total_output

            # Per-model breakdown
            by_model: Dict[str, dict] = {}
            for c in self.calls:
                key = f"{c.provider}/{c.model}"
                if key not in by_model:
                    by_model[key] = {
                        "model": c.model,
                        "provider": c.provider,
                        "calls": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0,
                        "cost": 0.0,
                    }
                by_model[key]["calls"] += 1
                by_model[key]["input_tokens"] += c.input_tokens
                by_model[key]["output_tokens"] += c.output_tokens
                by_model[key]["total_tokens"] += c.input_tokens + c.output_tokens
                by_model[key]["cost"] += c.cost

            num_cases = len(set(c.case_id for c in self.calls if c.case_id))

            return {
                "total_calls": total_calls,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "avg_tokens_per_request": total_tokens / num_cases if num_cases else 0,
                "avg_cost_per_request": total_cost / num_cases if num_cases else 0,
                "num_cases": num_cases,
                "by_model": by_model,
            }

    def save_report(self, filepath: str):
        """Save a usage report to a file."""
        summary = self.get_summary()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
