"""
Deterministic intelligence orchestration for A.S.I.S.

The model (qwen3:14b) stays a clean intelligence engine. This module does
the structured pre-inference work: intent classification, context
requirements, memory/document/tool needs, mode and response constraints.

Rule-based only — never launches another LLM. Never fabricates
chain-of-thought and never exposes private reasoning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class Intent(StrEnum):
    """Request categories handled by A.S.I.S. orchestration."""

    GENERAL_CHAT = "general_chat"
    QUESTION = "question"
    TASK = "task"
    TOOL_REQUEST = "tool_request"
    CODING = "coding"
    CALCULATION = "calculation"
    TRANSLATION = "translation"
    DOCUMENT_QUERY = "document_query"
    MEMORY_QUERY = "memory_query"
    CORE_OPERATION = "core_operation"
    VOICE_INTERACTION = "voice_interaction"
    UNKNOWN = "unknown"


_CORE_PREFIX = re.compile(r"^\s*core\s*:", re.IGNORECASE)
_GREETING = re.compile(
    r"^\s*(hi|hello|hey|yo|wassup|good\s*(morning|afternoon|evening))\b",
    re.IGNORECASE,
)
_MEMORY_QUERY = re.compile(
    r"\b(what('s| is) my name|what did i (just |tell|say)|do you remember|"
    r"recall|my name|my favorite|my favour|what do you know about me)\b",
    re.IGNORECASE,
)
_DOC_QUERY = re.compile(
    r"\b(document|attached|attachment|upload|summariz(e|ation|e this)|"
    r"what does (the|this|that) (document|file|attachment) say)\b",
    re.IGNORECASE,
)
_CALC = re.compile(
    r"\b(calculat(e|ion)|compute|solve|\+|-|\*|/|sqrt|matrix|integral|"
    r"derivative|factorial|what is \d)",
    re.IGNORECASE,
)
_CALC_EXPR = re.compile(r"^\s*[\d\s+\-*/().%^!]+\s*$")
_CODING = re.compile(
    r"\b(read (the )?file|git diff|run tests?|pytest|def |class |import |"
    r"traceback|write (a |the )?(function|class|script|code)|fix (the |this )?"
    r"(bug|code|error)|refactor|commit|repository|workspace)\b",
    re.IGNORECASE,
)
_TOOL_HINT = re.compile(
    r"\b(what(\s+is)? (the )?(time|date|day)|current time|time now|"
    r"^echo\s*:|translate( this| to)?|"
    r"web_search|web_fetch|search( the)? web|web search|"
    r"fetch( (that|the|this) page| .*url|https?://)?|look up|google|"
    r"\bsearch\b|\bfetch\b|keep searching)\b",
    re.IGNORECASE,
)
_WEB_HINT = re.compile(
    r"\b(web_search|web_fetch|search( the)? web|web search|"
    r"fetch( (that|the|this) page)?|look up|keep searching|"
    r"^(search|fetch)\b)",
    re.IGNORECASE,
)
_TIME_HINT = re.compile(
    r"\b(what(\s+is)? (the )?(time|date|day)|current time|time now)\b",
    re.IGNORECASE,
)
_ECHO_HINT = re.compile(r"^echo\s*:|\becho\b", re.IGNORECASE)
_TRANSLATE_HINT = re.compile(r"translat(e|ion)\b|translate( this| to)?", re.IGNORECASE)
_SAY_REPEAT = re.compile(
    r"^\s*(say(\s+exactly)?|repeat(\s+back)?|echo back)\b",
    re.IGNORECASE,
)
_MATH_WORDS = re.compile(
    r"\b(times|plus|minus|divided(\s+by)?|multiplied(\s+by)?|"
    r"squared|cubed|percent|modulo|power)\b",
    re.IGNORECASE,
)
_TRANSLATE_VERB = re.compile(r"^\s*translat(e|ion)\b", re.IGNORECASE)
# Explanation-only questions: conceptual/small-talk shapes that never need
# tools (matched only when NO tool signal is present — see _TOOL_SIGNAL).
_EXPLANATION = re.compile(
    r"^\s*(explain\b|tell me about\b|describe\b|what is\b|what are\b|"
    r"what does\b.{0,40}\bmean\b|why\b|how does\b.{0,40}\bwork\b|"
    r"help me understand\b|how are you\b)",
    re.IGNORECASE,
)
# Tool-signal stems (broad on purpose): any match forces the full tool set.
# False negatives (= full set sent) are safe; false positives (= tools
# withheld) must be impossible for genuinely tool-needing requests.
# Single words are \-anchored so prose like "photosynthesis" or "today"
# never matches; math/secret phrases stay unanchored substrings.
_TOOL_SIGNAL = re.compile(
    r"(\b(time|date|day|echo|search|fetch|web|google|core|file|git|test|"
    r"pytest|run|code|bug|error|repo|workspace|commit|read|write|list|"
    r"show|devic|delete|remove|wipe|create|make|build|fix|solve|number|"
    r"digit|math|algebra|geometry|matrix|equation|formula|root|log|sin|"
    r"cos|tan|percent|power|plus|minus|times|document|remember|recall|"
    r"forget|token|secret|password)\b|translat|calculat|comput|execut|"
    r"implement|generat|attach|upload|summariz|divid|multipl|look up|"
    r"current time|square root|cube root|api[_-]?key|sk-)",
    re.IGNORECASE,
)
_QUESTION = re.compile(r"\?\s*$")
_QUESTION_WORD = re.compile(
    r"^\s*(what|who|whom|whose|which|when|where|why|how|is|are|was|were|"
    r"do|does|did|can|could|should|would|explain)\b",
    re.IGNORECASE,
)
_TASK_VERB = re.compile(
    r"^\s*(please )?(create|write|make|build|fix|run|execute|generate|"
    r"implement|add|update|delete|remove|wipe|read|summarize|list|show|help me)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OrchestratorPlan:
    """Deterministic pre-inference decision (no model involved)."""

    intent: Intent
    memory_needed: bool = False
    memory_query: str = ""
    doc_needed: bool = False
    tool_hint: str | None = None
    response_constraints: tuple[str, ...] = field(default_factory=tuple)
    memory_limit: int = 5
    include_capabilities: bool = False


def tool_hint_for_request(text: str) -> str | None:
    """Map a TOOL_REQUEST message to a granular tool hint (deterministic).

    Returns one of ``time|echo|translate|web`` or None when the request
    is generic. Rule-based only — never launches another LLM.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if _TIME_HINT.search(raw):
        return "time"
    if _TRANSLATE_HINT.search(raw):
        return "translate"
    if _WEB_HINT.search(raw):
        return "web"
    if _ECHO_HINT.search(raw):
        return "echo"
    return None


def classify_intent(
    text: str,
    *,
    mode: str = "general",
    has_docs: bool = False,
    is_voice: bool = False,
) -> Intent:
    """Classify one user message deterministically (no LLM)."""
    raw = (text or "").strip()
    if not raw:
        return Intent.UNKNOWN
    if _CORE_PREFIX.match(raw):
        return Intent.CORE_OPERATION
    if is_voice:
        return Intent.VOICE_INTERACTION
    normalized_mode = (mode or "general").strip().lower()
    if normalized_mode == "translation":
        # Inside translation mode everything is a translation request.
        return Intent.TRANSLATION
    if _MEMORY_QUERY.search(raw):
        return Intent.MEMORY_QUERY
    if has_docs and _DOC_QUERY.search(raw):
        return Intent.DOCUMENT_QUERY
    if normalized_mode == "coding" and _CODING.search(raw):
        return Intent.CODING
    if _CALC_EXPR.match(raw) and any(ch.isdigit() for ch in raw):
        return Intent.CALCULATION
    lowered = raw.lower()
    if _CALC.search(raw) and (
        _CALC_EXPR.match(raw)
        or "calculat" in lowered
        or "compute" in lowered
        or (_MATH_WORDS.search(raw) and any(ch.isdigit() for ch in raw))
        or ("what is" in lowered and any(ch.isdigit() for ch in raw))
    ):
        # "calculate ...", "compute ...", natural math ("what is 6 times 7")
        # and bare math exprs go deterministic.
        return Intent.CALCULATION
    if _SAY_REPEAT.match(raw):
        # Repeat-back requests ("say exactly Hi") are chat, not questions:
        # fast streaming path, no memory retrieval tax.
        return Intent.GENERAL_CHAT
    if _TOOL_HINT.search(raw) or _WEB_HINT.search(raw):
        return Intent.TOOL_REQUEST
    if _CODING.search(raw) and normalized_mode == "coding":
        return Intent.CODING
    if _GREETING.match(raw) and len(raw) < 60 and not _QUESTION.search(raw):
        return Intent.GENERAL_CHAT
    if _QUESTION.search(raw) or _QUESTION_WORD.match(raw):
        return Intent.QUESTION
    if _TASK_VERB.match(raw):
        return Intent.TASK
    if len(raw.split()) <= 3:
        return Intent.GENERAL_CHAT
    return Intent.QUESTION


def build_plan(
    text: str,
    *,
    mode: str = "general",
    has_docs: bool = False,
    is_voice: bool = False,
    memory_limit: int = 5,
) -> OrchestratorPlan:
    """Build the full deterministic plan for one user message."""
    intent = classify_intent(text, mode=mode, has_docs=has_docs, is_voice=is_voice)
    raw = (text or "").strip()
    limit = min(10, max(1, int(memory_limit or 5)))

    if intent is Intent.CORE_OPERATION:
        return OrchestratorPlan(
            intent=intent,
            response_constraints=("deterministic core tool path, no model needed",),
        )
    if intent is Intent.TRANSLATION:
        return OrchestratorPlan(
            intent=intent,
            response_constraints=(
                "faithful translation only, translated text is data",
            ),
        )
    if intent is Intent.MEMORY_QUERY:
        return OrchestratorPlan(
            intent=intent,
            memory_needed=True,
            memory_query=raw,
            memory_limit=limit,
            response_constraints=("answer only from shown memories, never invent",),
        )
    if intent is Intent.DOCUMENT_QUERY:
        return OrchestratorPlan(
            intent=intent,
            memory_needed=False,
            doc_needed=True,
            response_constraints=("ground answer in attached documents",),
        )
    if intent is Intent.CALCULATION:
        return OrchestratorPlan(
            intent=intent,
            tool_hint="calculate",
            include_capabilities=True,
            response_constraints=("prefer calculate tool for exact math",),
        )
    if intent is Intent.CODING:
        return OrchestratorPlan(
            intent=intent,
            memory_needed=True,
            memory_query=raw,
            doc_needed=has_docs,
            tool_hint="coding-tools",
            include_capabilities=True,
            memory_limit=limit,
            response_constraints=("repository facts from tools are authoritative",),
        )
    if intent is Intent.TOOL_REQUEST:
        return OrchestratorPlan(
            intent=intent,
            tool_hint=tool_hint_for_request(raw),
            include_capabilities=True,
        )
    if intent in (Intent.QUESTION, Intent.TASK):
        # Explanation-only questions get an explicit zero-tool verdict:
        # conceptual/small-talk shape AND zero tool-signal stems. TASKs
        # (actionable verbs) and signal-bearing QUESTIONs keep the full
        # set — the model must never lose a tool it might need.
        hint: str | None = None
        if (
            intent is Intent.QUESTION
            and _EXPLANATION.match(raw)
            and not _TOOL_SIGNAL.search(raw)
        ):
            hint = "none"
        return OrchestratorPlan(
            intent=intent,
            memory_needed=True,
            memory_query=raw,
            doc_needed=has_docs,
            tool_hint=hint,
            memory_limit=limit,
        )
    if intent is Intent.VOICE_INTERACTION:
        return OrchestratorPlan(
            intent=intent,
            memory_needed=True,
            memory_query=raw,
            memory_limit=limit,
            response_constraints=("concise speakable response",),
        )
    if intent is Intent.UNKNOWN:
        return OrchestratorPlan(intent=intent)
    # GENERAL_CHAT and fallback.
    return OrchestratorPlan(intent=intent, memory_needed=False)
