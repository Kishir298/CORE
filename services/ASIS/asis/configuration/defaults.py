"""
A.S.I.S. default configuration values.

Safe built-in defaults only. Machine-specific values and secrets must
come from environment variables or user configuration files.
"""

# Application
APP_NAME = "A.S.I.S."
APP_VERSION = "0.1.0"

# Identity
IDENTITY_TITLE = "A Smart Intelligence System"
SHUTDOWN_PHRASE = "asis shutdown"

# Runtime
DEBUG = False
LOG_LEVEL = "INFO"

# AI provider
AI_PROVIDER = "ollama"
AI_MODEL = "qwen3:14b"
AI_ENDPOINT = "http://127.0.0.1:11434"

# AI behavior
AI_REQUEST_TIMEOUT = 120
AI_TEMPERATURE = 0.7
AI_MAX_CONTEXT_MESSAGES = 20
AI_CONTEXT_CHAR_LIMIT = 12_000
# Native LLM function calling: "auto" (try native, fall back to
# heuristics), "true" (native required when the provider supports it),
# "false" (heuristics only).
AI_NATIVE_TOOLS = "auto"
# Model thinking (qwen3-class): "auto" disables thinking for known
# thinking-model families, "true"/"false" force it. Verified on
# Ollama 0.34.1 + qwen3:14b: false skips generation (2.5s vs 79s).
AI_THINK = "auto"
# Max tokens to predict per request (0 = server default/unset).
AI_NUM_PREDICT = 0
# Keep the model loaded between turns ("" = server default).
AI_KEEP_ALIVE = "30m"

# Ollama lifecycle ownership (A.S.I.S.-started `ollama serve` only).
# MANAGED: "auto" (connect if running, else start owned), "on" (always
# ensure owned when down), "off" (never start; fail fast with guidance).
OLLAMA_MANAGED = "auto"
# How long to wait for a freshly started `ollama serve` to answer /api/tags.
OLLAMA_SERVE_TIMEOUT = 60
# Bounded graceful shutdown for an A.S.I.S.-owned Ollama process.
OLLAMA_SHUTDOWN_TIMEOUT = 10

# Boot model readiness probe
# Overall timeout for the readiness probe (cold loads can be slow).
BOOT_READINESS_TIMEOUT = 120
# Max tokens for the probe request (bounded, small for fast response).
BOOT_PROBE_NUM_PREDICT = 32
# Disable thinking for the probe (faster, avoids thinking-model overhead).
BOOT_PROBE_DISABLE_THINK = True
# Require non-empty visible content in probe response.
BOOT_PROBE_REQUIRE_VISIBLE = True

# Conversation
CONVERSATION_MAX_HISTORY = 20

# Memory
MEMORY_PROVIDER = "local"
MEMORY_DATABASE_NAME = "memory.db"

# Voice
VOICE_SAMPLE_RATE = 16_000
VOICE_CHANNELS = 1
VOICE_BLOCK_SIZE = 1_024
VOICE_INPUT_ENGINE = "mock"
VOICE_OUTPUT_ENGINE = "mock"
VOICE_STT_ENGINE = "mock"
VOICE_STT_MODEL = "small"
VOICE_STT_DEVICE = "cpu"
VOICE_STT_COMPUTE_TYPE = "int8"
VOICE_STT_LANGUAGE = ""
VOICE_TTS_ENGINE = "mock"
VOICE_TTS_VOICE = "male-default"
VOICE_TTS_SAMPLE_RATE = 16_000
VOICE_SPEAKER_ENGINE = "mock"
VOICE_SPEAKER_MODEL = "speechbrain/spkrec-ecapa-voxceleb"
VOICE_SPEAKER_DEVICE = "cpu"
VOICE_SPEAKER_CONFIDENCE = 0.6
VOICE_SPEAKER_THRESHOLD = 0.6
VOICE_SPEAKER_METRIC = "cosine"
VOICE_WAKE_WORD = "hey asis"
VOICE_WAKE_ENGINE = "mock"
VOICE_WAKE_THRESHOLD = 0.5
VOICE_WAKE_MODEL = ""
VOICE_VAD_ENGINE = "mock"
VOICE_VAD_THRESHOLD = 0.5
VOICE_MAX_UTTERANCE_S = 15.0
VOICE_SILENCE_S = 0.8

# Network
NETWORK_TIMEOUT = 10
NETWORK_RETRIES = 3

# Tool execution
TOOL_TIMEOUT = 30
# Maximum validated native tool calls per assistant turn (1-10).
TOOL_MAX_CALLS_PER_TURN = 3

# Basic web access (optional capability; standalone by default)
WEB_ENABLED = False
WEB_SEARCH_PROVIDER = "duckduckgo"
WEB_TIMEOUT = 10
WEB_MAX_RESULTS = 5
WEB_MAX_CHARS = 8_000
WEB_MAX_RESPONSE_BYTES = 1_000_000
WEB_MAX_REDIRECTS = 3
WEB_MAX_QUERY_LENGTH = 500
WEB_MAX_URL_LENGTH = 2_000

# Update system (offline-first, optional online auto-updates)
UPDATE_ENABLED = True
UPDATE_CHECK_ON_STARTUP = True
UPDATE_AUTO_INSTALL = True
UPDATE_CHECK_INTERVAL_HOURS = 24
UPDATE_NETWORK_TIMEOUT = 3
UPDATE_SKIP_COMPONENTS = ""

# Translation engine (optional local capability; mock backend by default)
TRANSLATION_ENABLED = True
TRANSLATION_PROVIDER = "mock"
TRANSLATION_MODEL = "google/madlad400-3b-mt"
TRANSLATION_MODEL_PATH = ""
TRANSLATION_DEVICE = "cpu"
TRANSLATION_CACHE_ENABLED = True
TRANSLATION_CACHE_SIZE = 200
TRANSLATION_DEFAULT_SOURCE = "auto"
TRANSLATION_DEFAULT_TARGET = "en"
TRANSLATION_MAX_CHARS = 5_000

# Calculator engine (local deterministic mathematics, SymPy-backed)
CALCULATOR_ENABLED = True
CALCULATOR_MAX_EXPRESSION_CHARS = 2_000
CALCULATOR_MAX_MATRIX_SIZE = 10
CALCULATOR_TIMEOUT = 30
CALCULATOR_PRECISION = 10
CALCULATOR_ANGLE_MODE = "radians"

# Security / permissions
REQUIRE_CONFIRMATION_FOR_DANGEROUS = True

# Runtime
SHUTDOWN_TIMEOUT = 10

# C.O.R.E. integration (optional; standalone by default)
CORE_ENABLED = False
CORE_HOST = "127.0.0.1"
CORE_PORT = 5000
CORE_DEVICE_FILE = ""
CORE_CA_FILE = ""
CORE_INSECURE = False
CORE_CONNECT_TIMEOUT = 10
CORE_REQUEST_TIMEOUT = 30
CORE_RECONNECT_ENABLED = True
CORE_RECONNECT_DELAY = 5

# Assistant modes (A.S.C.S. is the coding mode of A.S.I.S.)
DEFAULT_MODE = "general"

# Coding workspace (A.S.C.S.)
CODING_WORKSPACE = ""
CODING_COMMAND_TIMEOUT = 120
CODING_MAX_FILE_SIZE = 200_000
CODING_MAX_OUTPUT_SIZE = 60_000

# A.S.C.S. Integration (optional; standalone by default)
ASCS_ENABLED = False
ASCS_INVOKE_MODE = "subprocess"  # "subprocess" | "api"
ASCS_WORKSPACE = ""
ASCS_MODE = "AUTO"
ASCS_INTELLIGENCE = "high"
ASCS_COMMAND_TIMEOUT = 120
ASCS_REQUEST_TIMEOUT = 600
ASCS_MODEL = "qwen3-coder:30b"
ASCS_FALLBACK_MODEL = "qwen2.5-coder:14b"
ASCS_MAX_ITERATIONS = 50
ASCS_HANDOVER_ENABLED = True

# TUI (Terminal User Interface) - persistent user preferences
TUI_SIDEBAR_COLLAPSED = False
TUI_THEME = "dark"
TUI_LEFT_COLUMN_WIDTH = 28
