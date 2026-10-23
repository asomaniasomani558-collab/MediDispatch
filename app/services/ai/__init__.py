"""AI harness package. ``get_harness()`` returns the app-wide instance."""

from flask import current_app

from .llm_harness import AIAssessment, AIUnavailable, DisabledHarness, OllamaHarness


def init_app(app) -> None:
    if app.config.get("AI_ENABLED"):
        app.extensions["ai_harness"] = OllamaHarness.from_config(app.config)
    else:
        app.extensions["ai_harness"] = DisabledHarness()


def get_harness():
    return current_app.extensions.get("ai_harness") or DisabledHarness()


__all__ = ["AIAssessment", "AIUnavailable", "DisabledHarness", "OllamaHarness",
           "get_harness", "init_app"]
