from enum import Enum


class RuntimeState(str, Enum):
    STARTING = "starting"
    INITIALIZING = "initializing"
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"
    FAILED = "failed"
