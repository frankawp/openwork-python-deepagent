from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    id: str
    name: str


@dataclass(frozen=True)
class ModelConfig:
    id: str
    name: str
    provider: str
    model: str
    description: str
    available: bool = True


PROVIDERS = [
    Provider(id="anthropic", name="Anthropic"),
    Provider(id="openai", name="OpenAI"),
    Provider(id="google", name="Google"),
    Provider(id="deepseek", name="DeepSeek"),
]

# Shared model catalog used by the BS backend and browser UI.
MODELS = [
    ModelConfig(
        id="claude-opus-4-5-20251101",
        name="Claude Opus 4.5",
        provider="anthropic",
        model="claude-opus-4-5-20251101",
        description="Premium model with maximum intelligence",
    ),
    ModelConfig(
        id="claude-sonnet-4-5-20250929",
        name="Claude Sonnet 4.5",
        provider="anthropic",
        model="claude-sonnet-4-5-20250929",
        description="Best balance of intelligence, speed, and cost for agents",
    ),
    ModelConfig(
        id="claude-haiku-4-5-20251001",
        name="Claude Haiku 4.5",
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        description="Fastest model with near-frontier intelligence",
    ),
    ModelConfig(
        id="claude-opus-4-1-20250805",
        name="Claude Opus 4.1",
        provider="anthropic",
        model="claude-opus-4-1-20250805",
        description="Previous generation premium model with extended thinking",
    ),
    ModelConfig(
        id="claude-sonnet-4-20250514",
        name="Claude Sonnet 4",
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        description="Fast and capable previous generation model",
    ),
    ModelConfig(
        id="gpt-5.2",
        name="GPT-5.2",
        provider="openai",
        model="gpt-5.2",
        description="Latest flagship with enhanced coding and agentic capabilities",
    ),
    ModelConfig(
        id="gpt-5.1",
        name="GPT-5.1",
        provider="openai",
        model="gpt-5.1",
        description="Advanced reasoning and robust performance",
    ),
    ModelConfig(
        id="o3",
        name="o3",
        provider="openai",
        model="o3",
        description="Advanced reasoning for complex problem-solving",
    ),
    ModelConfig(
        id="o3-mini",
        name="o3 Mini",
        provider="openai",
        model="o3-mini",
        description="Cost-effective reasoning with faster response times",
    ),
    ModelConfig(
        id="o4-mini",
        name="o4 Mini",
        provider="openai",
        model="o4-mini",
        description="Fast, efficient reasoning model succeeding o3",
    ),
    ModelConfig(
        id="o1",
        name="o1",
        provider="openai",
        model="o1",
        description="Premium reasoning for research, coding, math and science",
    ),
    ModelConfig(
        id="gpt-4.1",
        name="GPT-4.1",
        provider="openai",
        model="gpt-4.1",
        description="Strong instruction-following with 1M context window",
    ),
    ModelConfig(
        id="gpt-4.1-mini",
        name="GPT-4.1 Mini",
        provider="openai",
        model="gpt-4.1-mini",
        description="Faster, smaller version balancing performance and efficiency",
    ),
    ModelConfig(
        id="gpt-4.1-nano",
        name="GPT-4.1 Nano",
        provider="openai",
        model="gpt-4.1-nano",
        description="Most cost-efficient for lighter tasks",
    ),
    ModelConfig(
        id="gpt-4o",
        name="GPT-4o",
        provider="openai",
        model="gpt-4o",
        description="Versatile model for text generation and comprehension",
    ),
    ModelConfig(
        id="gpt-4o-mini",
        name="GPT-4o Mini",
        provider="openai",
        model="gpt-4o-mini",
        description="Cost-efficient variant with faster response times",
    ),
    ModelConfig(
        id="gemini-3-pro-preview",
        name="Gemini 3 Pro Preview",
        provider="google",
        model="gemini-3-pro-preview",
        description="State-of-the-art reasoning and multimodal understanding",
    ),
    ModelConfig(
        id="gemini-3-flash-preview",
        name="Gemini 3 Flash Preview",
        provider="google",
        model="gemini-3-flash-preview",
        description="Fast frontier-class model with low latency and cost",
    ),
    ModelConfig(
        id="gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        provider="google",
        model="gemini-2.5-pro",
        description="High-capability model for complex reasoning and coding",
    ),
    ModelConfig(
        id="gemini-2.5-flash",
        name="Gemini 2.5 Flash",
        provider="google",
        model="gemini-2.5-flash",
        description="Lightning-fast with balance of intelligence and latency",
    ),
    ModelConfig(
        id="gemini-2.5-flash-lite",
        name="Gemini 2.5 Flash Lite",
        provider="google",
        model="gemini-2.5-flash-lite",
        description="Lightweight for low-cost, high-throughput use cases",
    ),
    ModelConfig(
        id="deepseek-chat",
        name="DeepSeek Chat",
        provider="deepseek",
        model="deepseek-chat",
        description="General chat model (OpenAI-compatible)",
    ),
    ModelConfig(
        id="deepseek-reasoner",
        name="DeepSeek Reasoner",
        provider="deepseek",
        model="deepseek-reasoner",
        description="Reasoning-focused model (OpenAI-compatible)",
    ),
]

DEFAULT_MODEL_ID = "claude-sonnet-4-5-20250929"
