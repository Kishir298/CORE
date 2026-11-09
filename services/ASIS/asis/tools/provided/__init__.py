"""
Safe built-in tools shipped with A.S.I.S.

These are the pattern for capability tools. Dangerous or system-affecting
tools must be declared with a higher PermissionLevel and approved by the
permission system via the ToolExecutor.
"""

from .ascs_integration import (
    AscsHandoverTool,
    AscsIntegrationTool,
    AscsStatusTool,
    build_ascs_tools,
    register_ascs_tools,
)
from .calculator_tools import (
    CalculateTool,
    build_calculator_tools,
    register_calculator_tools,
)
from .core_tools import (
    CoreAgentRequestTool,
    CoreDataRequestTool,
    CoreDeviceInfoTool,
    CoreDiscoverDevicesTool,
    CoreSendToDeviceTool,
    CoreServiceRequestTool,
    CoreStatusTool,
    build_core_tools,
    register_core_tools,
)
from .echo import EchoTool
from .time import CurrentTimeTool
from .translation_tools import (
    TranslateTextTool,
    build_translation_tools,
    register_translation_tools,
)
from .web_tools import (
    WebFetchTool,
    WebSearchTool,
    build_web_tools,
    register_web_tools,
)

__all__ = [
    "EchoTool",
    "CurrentTimeTool",
    "CalculateTool",
    "build_calculator_tools",
    "register_calculator_tools",
    "TranslateTextTool",
    "build_translation_tools",
    "register_translation_tools",
    "WebFetchTool",
    "WebSearchTool",
    "build_web_tools",
    "register_web_tools",
    "CoreAgentRequestTool",
    "CoreDataRequestTool",
    "CoreDeviceInfoTool",
    "CoreDiscoverDevicesTool",
    "CoreSendToDeviceTool",
    "CoreServiceRequestTool",
    "CoreStatusTool",
    "build_core_tools",
    "register_core_tools",
    "AscsIntegrationTool",
    "AscsHandoverTool",
    "AscsStatusTool",
    "build_ascs_tools",
    "register_ascs_tools",
]
