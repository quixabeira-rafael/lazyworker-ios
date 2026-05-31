from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from lazyworker.bootstrap.errors import BootstrapError
from lazyworker.bootstrap.forward import PortForwarder
from lazyworker.bootstrap.process import ProcessManager, SubprocessProcessManager
from lazyworker.bootstrap.readiness import wait_until_ready
from lazyworker.bootstrap.serverurl import wait_for_server_url
from lazyworker.bootstrap.simulator import SimulatorController
from lazyworker.bootstrap.state import (
    RunState,
    clear_run_state,
    load_run_state,
    save_run_state,
)
from lazyworker.bootstrap.wda import (
    SigningOptions,
    WdaBuilder,
    WdaLauncher,
    WdaProject,
    WdaProvisioner,
)
from lazyworker.devices.runner import CommandRunner, SubprocessRunner
from lazyworker.wda.client import WdaClient
from lazyworker.wda.errors import WdaError

DEFAULT_STATE_DIR = Path.home() / ".lazyworker"
SIMULATOR_KIND = "simulator"
DEVICE_KIND = "device"


class BootstrapService:
    """Orchestrates building, launching and tearing down WebDriverAgent on a simulator."""

    def __init__(
        self,
        *,
        runner: CommandRunner,
        process_manager: ProcessManager,
        project: WdaProject,
        state_dir: Path,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._project = project
        self._process_manager = process_manager
        self._state_dir = state_dir
        self._sleep = sleep
        self._simulator = SimulatorController(runner)
        self._provisioner = WdaProvisioner(runner, project)
        self._builder = WdaBuilder(runner, project)
        self._launcher = WdaLauncher(process_manager, project)
        self._forwarder = PortForwarder(process_manager)

    @classmethod
    def default(cls, *, state_dir: Path | None = None) -> BootstrapService:
        resolved = state_dir or DEFAULT_STATE_DIR
        project = WdaProject(
            source_dir=resolved / "WebDriverAgent",
            derived_data_dir=resolved / "DerivedData",
        )
        return cls(
            runner=SubprocessRunner(),
            process_manager=SubprocessProcessManager(),
            project=project,
            state_dir=resolved,
        )

    def bootstrap(self, *, signing: SigningOptions | None = None) -> None:
        """Fetch the WebDriverAgent source and build it.

        Without ``signing`` it builds for the simulator; with ``signing`` it
        patches the runner bundle id and builds a signed device variant.
        """
        self._provisioner.ensure_source()
        if signing is None:
            self._builder.build_for_testing()
        else:
            self._provisioner.set_runner_bundle_id(signing.runner_bundle_id)
            self._builder.build_device(signing)

    def up(
        self,
        udid: str,
        *,
        base_url: str,
        port: int,
        timeout: float = 180.0,
        probe: Callable[[], bool] | None = None,
    ) -> RunState:
        """Boot the simulator, launch WDA and wait until it is ready."""
        self._simulator.boot(udid)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._state_dir / "wda.log"
        process = self._launcher.launch(udid, log_path=log_path)

        if probe is None:
            probe = _status_probe(base_url)

        if not wait_until_ready(probe, timeout=timeout, sleep=self._sleep):
            self._process_manager.terminate(process.pid)
            raise BootstrapError(
                f"WebDriverAgent did not become ready within {timeout:.0f}s; see {log_path}"
            )

        state = RunState(
            udid=udid,
            port=port,
            pid=process.pid,
            base_url=base_url,
            kind=SIMULATOR_KIND,
        )
        save_run_state(state, self._state_dir)
        return state

    def up_device(
        self,
        udid: str,
        *,
        signing: SigningOptions,
        base_url: str,
        port: int,
        connection: str = "usb",
        local_port: int = 8100,
        device_port: int = 8100,
        timeout: float = 240.0,
        probe: Callable[[], bool] | None = None,
    ) -> RunState:
        """Launch WDA on a physical device and wait until ready.

        ``connection='usb'`` forwards the port via iproxy and talks to ``base_url``;
        ``connection='network'`` reads WDA's advertised LAN URL and talks to it directly.
        """
        self._state_dir.mkdir(parents=True, exist_ok=True)
        wda_log = self._state_dir / "wda-device.log"
        wda_process = self._launcher.launch_device(udid, signing, log_path=wda_log)

        forward_process = None
        if connection == "network":
            effective_url = wait_for_server_url(wda_log, timeout=timeout, sleep=self._sleep)
            if effective_url is None:
                self._process_manager.terminate(wda_process.pid)
                raise BootstrapError(
                    f"WebDriverAgent did not advertise a server URL within {timeout:.0f}s; "
                    f"see {wda_log}"
                )
        else:
            forward_process = self._forwarder.start(
                udid,
                local_port=local_port,
                device_port=device_port,
                log_path=self._state_dir / "iproxy.log",
            )
            effective_url = base_url

        if probe is None:
            probe = _status_probe(effective_url)

        if not wait_until_ready(probe, timeout=timeout, sleep=self._sleep):
            if forward_process is not None:
                self._process_manager.terminate(forward_process.pid)
            self._process_manager.terminate(wda_process.pid)
            raise BootstrapError(
                f"WebDriverAgent did not become ready within {timeout:.0f}s; see {wda_log}"
            )

        state = RunState(
            udid=udid,
            port=port,
            pid=wda_process.pid,
            base_url=effective_url,
            kind=DEVICE_KIND,
            forward_pid=forward_process.pid if forward_process is not None else None,
        )
        save_run_state(state, self._state_dir)
        return state

    def down(self, *, shutdown_simulator: bool = False) -> RunState | None:
        """Terminate the running WDA process (and port-forward) and clear state."""
        state = load_run_state(self._state_dir)
        if state is None:
            return None
        if state.forward_pid is not None:
            self._process_manager.terminate(state.forward_pid)
        self._process_manager.terminate(state.pid)
        if shutdown_simulator and state.kind == SIMULATOR_KIND:
            self._simulator.shutdown(state.udid)
        clear_run_state(self._state_dir)
        return state


def _status_probe(base_url: str) -> Callable[[], bool]:
    def probe() -> bool:
        try:
            with WdaClient(base_url) as client:
                return client.status().ready
        except WdaError:
            return False

    return probe
