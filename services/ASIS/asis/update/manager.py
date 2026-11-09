"""
Update Manager - coordinates all update checkers and installers.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field

from asis.configuration.settings import settings

from .checkers import ComponentUpdate
from .checkers.git import GitChecker
from .checkers.ollama import OllamaModelChecker
from .checkers.pip import PipChecker
from .detectors import NetworkDetector
from .installers.git import GitInstaller
from .installers.ollama import OllamaModelInstaller
from .installers.pip import PipInstaller

logger = logging.getLogger(__name__)


@dataclass
class UpdateResult:
    """Aggregated result of all update checks."""

    timestamp: float
    online: bool
    components: dict[str, ComponentUpdate] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def has_updates(self) -> bool:
        """True if any component has updates available."""
        return any(c.has_update for c in self.components.values())

    @property
    def updatable_components(self) -> list[str]:
        """List of component names that have updates."""
        return [name for name, c in self.components.items() if c.has_update]


class UpdateManager:
    """
    Manages update checking and installation for all ASIS components.

    Features:
    - Offline-first: never blocks startup
    - Parallel checking of all components
    - Configurable auto-install
    - Restart coordination
    """

    def __init__(
        self,
        network_detector: NetworkDetector | None = None,
        config: dict | None = None,
    ):
        self._network = network_detector or NetworkDetector(
            timeout=settings.update_network_timeout if hasattr(settings, "update_network_timeout") else 3.0,
            cache_ttl=300.0,
        )
        self._config = config or {}
        self._last_result: UpdateResult | None = None
        self._check_lock = threading.Lock()
        self._check_task: asyncio.Task | None = None

        # Initialize checkers and installers
        self._checkers = {
            "git": GitChecker(),
            "pip": PipChecker(),
            "ollama_models": OllamaModelChecker(model=getattr(settings, "ai_model", None)),
        }
        self._installers = {
            "git": GitInstaller(),
            "pip": PipInstaller(),
            "ollama_models": OllamaModelInstaller(model=getattr(settings, "ai_model", None)),
        }

        # Components to skip (from config)
        self._skip_components = set(self._config.get("skip_components", []))
        self._auto_install = self._config.get("auto_install", True)

    def check_all(self, force_network: bool = False) -> UpdateResult:
        """
        Check all components for updates.

        Runs network detection first, then checks components in parallel.
        If offline, returns cached/offline results without network calls.
        """
        with self._check_lock:
            # Check network
            online = self._network.check(force=force_network)

            result = UpdateResult(
                timestamp=time.time(),
                online=online,
            )

            if not online:
                logger.info("Network unavailable, skipping update checks")
                result.components = self._get_offline_results()
                self._last_result = result
                return result

            # Online: run all checkers in parallel
            result.components = self._run_checks_parallel()
            self._last_result = result
            return result

    def _get_offline_results(self) -> dict[str, ComponentUpdate]:
        """Return offline placeholder results for all components."""
        offline_results = {}
        for name, checker in self._checkers.items():
            if name in self._skip_components:
                continue
            try:
                # Run checker but it will fail gracefully without network
                update = checker.check()
                update.description = f"[offline] {update.description}"
                offline_results[name] = update
            except Exception as e:
                offline_results[name] = ComponentUpdate(
                    component=name,
                    current_version="unknown",
                    available_version="",
                    description=f"[offline] Check failed: {e}",
                )
        return offline_results

    def _run_checks_parallel(self) -> dict[str, ComponentUpdate]:
        """Run all checkers in parallel using threads."""
        import concurrent.futures

        results = {}
        errors = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_name = {
                executor.submit(checker.check): name
                for name, checker in self._checkers.items()
                if name not in self._skip_components
            }

            for future in concurrent.futures.as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    results[name] = future.result(timeout=60)
                except Exception as e:
                    errors[name] = str(e)
                    results[name] = ComponentUpdate(
                        component=name,
                        current_version="error",
                        available_version="",
                        description=f"Check failed: {e}",
                    )

        return results

    async def check_all_async(self, force_network: bool = False) -> UpdateResult:
        """Async version of check_all."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.check_all, force_network)

    def auto_install(self, result: UpdateResult | None = None) -> dict[str, bool]:
        """
        Automatically install available updates.

        Args:
            result: UpdateResult from check_all(). If None, runs check_all() first.

        Returns:
            Dict of component -> success status.
        """
        if result is None:
            result = self.check_all()

        if not self._auto_install:
            logger.info("Auto-install disabled")
            return {}

        if not result.online:
            logger.info("Offline, skipping auto-install")
            return {}

        install_results = {}
        for component_name in result.updatable_components:
            if component_name in self._skip_components:
                continue

            installer = self._installers.get(component_name)
            if not installer:
                logger.warning(f"No installer for {component_name}")
                install_results[component_name] = False
                continue

            update_info = result.components[component_name].metadata or {}
            update_info["component"] = component_name

            logger.info(f"Auto-installing update for {component_name}...")
            install_result = installer.install(update_info)
            install_results[component_name] = install_result.success

            if install_result.success and install_result.requires_restart:
                logger.info(f"{component_name} update requires restart")

        return install_results

    def install_component(self, component_name: str) -> bool:
        """Manually install update for a specific component."""
        if component_name not in self._installers:
            logger.error(f"No installer for {component_name}")
            return False

        result = self.check_all(force_network=True)
        if component_name not in result.components:
            logger.error(f"No update info for {component_name}")
            return False

        update_info = result.components[component_name].metadata or {}
        update_info["component"] = component_name

        installer = self._installers[component_name]
        install_result = installer.install(update_info)
        return install_result.success

    def get_status(self) -> dict:
        """Get current update status for UI/CLI."""
        result = self._last_result or self.check_all()
        return {
            "online": result.online,
            "last_check": result.timestamp,
            "has_updates": result.has_updates,
            "components": {
                name: {
                    "current": c.current_version,
                    "available": c.available_version,
                    "description": c.description,
                    "has_update": c.has_update,
                }
                for name, c in result.components.items()
            },
        }

    def start_background_checker(self, interval_hours: float = 24.0) -> None:
        """Start periodic background update checks."""
        if self._check_task is not None:
            return

        async def _background_loop():
            while True:
                try:
                    await asyncio.sleep(interval_hours * 3600)
                    logger.info("Running scheduled update check...")
                    result = await self.check_all_async()
                    if result.has_updates and self._auto_install:
                        await loop.run_in_executor(None, self.auto_install, result)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Background update check failed: {e}")

        loop = asyncio.get_event_loop()
        self._check_task = loop.create_task(_background_loop())

    def stop_background_checker(self) -> None:
        """Stop background update checks."""
        if self._check_task is not None:
            self._check_task.cancel()
            self._check_task = None


# Global manager instance
_manager: UpdateManager | None = None
_manager_lock = threading.Lock()


def get_update_manager(config: dict | None = None) -> UpdateManager:
    """Get or create the global update manager."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = UpdateManager(config=config)
        return _manager
