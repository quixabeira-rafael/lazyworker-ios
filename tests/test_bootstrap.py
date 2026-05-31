import time
from collections.abc import Sequence
from pathlib import Path

import pytest

from lazyworker.bootstrap.errors import BootstrapError
from lazyworker.bootstrap.forward import PortForwarder
from lazyworker.bootstrap.process import SubprocessProcessManager
from lazyworker.bootstrap.readiness import wait_until_ready
from lazyworker.bootstrap.serverurl import parse_server_url, wait_for_server_url
from lazyworker.bootstrap.service import BootstrapService
from lazyworker.bootstrap.simulator import SimulatorController
from lazyworker.bootstrap.state import (
    RunState,
    clear_run_state,
    load_run_state,
    save_run_state,
)
from lazyworker.bootstrap.wda import (
    DEFAULT_RUNNER_BUNDLE_ID,
    SigningOptions,
    WdaBuilder,
    WdaLauncher,
    WdaProject,
    WdaProvisioner,
)
from lazyworker.devices.runner import CommandError


class RecordingRunner:
    def __init__(self, errors: dict[str, CommandError] | None = None) -> None:
        self.calls: list[list[str]] = []
        self._errors = errors or {}

    def run(self, args: Sequence[str], *, timeout: float | None = None) -> str:
        self.calls.append(list(args))
        for marker, error in self._errors.items():
            if marker in args:
                raise error
        return ""


class FakeProcess:
    def __init__(self, pid: int) -> None:
        self._pid = pid
        self.terminated = False

    @property
    def pid(self) -> int:
        return self._pid

    def is_running(self) -> bool:
        return not self.terminated

    def terminate(self) -> None:
        self.terminated = True


class FakeProcessManager:
    def __init__(self) -> None:
        self.spawned: list[list[str]] = []
        self.terminated: list[int] = []
        self.processes: list[FakeProcess] = []
        self._next_pid = 4242

    def spawn(self, args: Sequence[str], *, log_path: Path | None = None) -> FakeProcess:
        self.spawned.append(list(args))
        process = FakeProcess(self._next_pid)
        self._next_pid += 1
        self.processes.append(process)
        return process

    def terminate(self, pid: int) -> None:
        self.terminated.append(pid)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _project(tmp_path: Path) -> WdaProject:
    return WdaProject(source_dir=tmp_path / "WebDriverAgent", derived_data_dir=tmp_path / "dd")


def _project_with_pbxproj(tmp_path: Path) -> WdaProject:
    project = _project(tmp_path)
    project.project_path.mkdir(parents=True)
    (project.project_path / "project.pbxproj").write_text(
        f"\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = {DEFAULT_RUNNER_BUNDLE_ID};\n"
    )
    return project


_SIGNING = SigningOptions(team_id="92K8JB9444", runner_bundle_id="com.lazyworker.wda.Runner")


def test_simulator_boot_tolerates_already_booted() -> None:
    runner = RecordingRunner(
        {"boot": CommandError(["boot"], 149, "Unable to boot device in current state: Booted")}
    )
    SimulatorController(runner).boot("U1")
    assert ["xcrun", "simctl", "boot", "U1"] in runner.calls


def test_simulator_boot_reraises_other_errors() -> None:
    runner = RecordingRunner({"boot": CommandError(["boot"], 1, "device not found")})
    with pytest.raises(CommandError):
        SimulatorController(runner).boot("U1")


def test_provisioner_clones_when_absent(tmp_path: Path) -> None:
    runner = RecordingRunner()
    WdaProvisioner(runner, _project(tmp_path)).ensure_source()
    assert any("clone" in call for call in runner.calls)


def test_provisioner_skips_when_present(tmp_path: Path) -> None:
    project = _project(tmp_path)
    project.project_path.mkdir(parents=True)
    runner = RecordingRunner()
    WdaProvisioner(runner, project).ensure_source()
    assert runner.calls == []


def test_builder_issues_build_for_testing(tmp_path: Path) -> None:
    runner = RecordingRunner()
    WdaBuilder(runner, _project(tmp_path)).build_for_testing()
    call = runner.calls[0]
    assert "build-for-testing" in call
    assert "CODE_SIGNING_ALLOWED=NO" in call


def test_launcher_spawns_test_without_building(tmp_path: Path) -> None:
    manager = FakeProcessManager()
    process = WdaLauncher(manager, _project(tmp_path)).launch("U1")
    assert process.pid == 4242
    call = manager.spawned[0]
    assert "test-without-building" in call
    assert "platform=iOS Simulator,id=U1" in call


def test_wait_until_ready_succeeds() -> None:
    clock = FakeClock()
    calls = {"n": 0}

    def probe() -> bool:
        calls["n"] += 1
        return calls["n"] >= 3

    def sleep(_: float) -> None:
        clock.now += 1.0

    assert wait_until_ready(probe, timeout=10, sleep=sleep, clock=clock) is True
    assert calls["n"] == 3


def test_wait_until_ready_times_out() -> None:
    clock = FakeClock()

    def sleep(_: float) -> None:
        clock.now += 1.0

    assert wait_until_ready(lambda: False, timeout=3, sleep=sleep, clock=clock) is False


def test_run_state_roundtrip(tmp_path: Path) -> None:
    state = RunState(udid="U1", port=8100, pid=99, base_url="http://x", kind="simulator")
    save_run_state(state, tmp_path)
    assert load_run_state(tmp_path) == state
    clear_run_state(tmp_path)
    assert load_run_state(tmp_path) is None


def test_service_up_orchestrates_and_persists(tmp_path: Path) -> None:
    runner = RecordingRunner()
    manager = FakeProcessManager()
    service = BootstrapService(
        runner=runner,
        process_manager=manager,
        project=_project(tmp_path),
        state_dir=tmp_path,
        sleep=lambda _: None,
    )

    state = service.up(
        "U1", base_url="http://127.0.0.1:8100", port=8100, probe=lambda: True
    )

    assert state.pid == 4242
    assert ["xcrun", "simctl", "boot", "U1"] in runner.calls
    assert manager.spawned, "WDA runner should be launched"
    assert load_run_state(tmp_path) == state


def test_service_up_times_out_and_terminates(tmp_path: Path) -> None:
    manager = FakeProcessManager()
    service = BootstrapService(
        runner=RecordingRunner(),
        process_manager=manager,
        project=_project(tmp_path),
        state_dir=tmp_path,
        sleep=lambda _: None,
    )

    with pytest.raises(BootstrapError):
        service.up("U1", base_url="http://x", port=8100, timeout=2, probe=lambda: False)

    assert manager.terminated == [4242]
    assert load_run_state(tmp_path) is None


def test_service_down_terminates_and_clears(tmp_path: Path) -> None:
    manager = FakeProcessManager()
    service = BootstrapService(
        runner=RecordingRunner(),
        process_manager=manager,
        project=_project(tmp_path),
        state_dir=tmp_path,
    )
    save_run_state(
        RunState(udid="U1", port=8100, pid=555, base_url="http://x", kind="simulator"),
        tmp_path,
    )

    state = service.down()

    assert state is not None
    assert manager.terminated == [555]
    assert load_run_state(tmp_path) is None


def test_service_down_when_nothing_running(tmp_path: Path) -> None:
    service = BootstrapService(
        runner=RecordingRunner(),
        process_manager=FakeProcessManager(),
        project=_project(tmp_path),
        state_dir=tmp_path,
    )
    assert service.down() is None


def test_set_runner_bundle_id_is_idempotent(tmp_path: Path) -> None:
    project = _project_with_pbxproj(tmp_path)
    provisioner = WdaProvisioner(RecordingRunner(), project)
    pbxproj = project.project_path / "project.pbxproj"

    provisioner.set_runner_bundle_id("com.lazyworker.wda.Runner")
    text = pbxproj.read_text()
    assert "com.lazyworker.wda.Runner" in text
    assert DEFAULT_RUNNER_BUNDLE_ID not in text

    provisioner.set_runner_bundle_id("com.lazyworker.wda.Runner")
    assert pbxproj.read_text() == text


def test_build_device_args(tmp_path: Path) -> None:
    runner = RecordingRunner()
    WdaBuilder(runner, _project(tmp_path)).build_device(_SIGNING)
    call = runner.calls[0]
    assert "build-for-testing" in call
    assert "generic/platform=iOS" in call
    assert "DEVELOPMENT_TEAM=92K8JB9444" in call
    assert "-allowProvisioningUpdates" in call


def test_launch_device_args(tmp_path: Path) -> None:
    manager = FakeProcessManager()
    WdaLauncher(manager, _project(tmp_path)).launch_device("UDID", _SIGNING)
    call = manager.spawned[0]
    assert "test-without-building" in call
    assert "platform=iOS,id=UDID" in call
    assert "DEVELOPMENT_TEAM=92K8JB9444" in call


def test_forwarder_starts_iproxy() -> None:
    manager = FakeProcessManager()
    PortForwarder(manager).start("UDID", local_port=8100, device_port=8100)
    assert manager.spawned[0] == ["iproxy", "8100:8100", "-u", "UDID"]


def test_parse_server_url() -> None:
    line = "... ServerURLHere->http://192.168.1.144:8100<-ServerURLHere ..."
    assert parse_server_url(line) == "http://192.168.1.144:8100"
    assert parse_server_url("no url here") is None


def test_wait_for_server_url(tmp_path: Path) -> None:
    log = tmp_path / "wda.log"
    log.write_text("boot\nServerURLHere->http://10.0.0.5:8100<-ServerURLHere\n")
    url = wait_for_server_url(log, timeout=5, sleep=lambda _: None)
    assert url == "http://10.0.0.5:8100"


def test_wait_for_server_url_times_out(tmp_path: Path) -> None:
    clock = FakeClock()
    log = tmp_path / "wda.log"
    log.write_text("nothing useful")

    def sleep(_: float) -> None:
        clock.now += 1.0

    assert wait_for_server_url(log, timeout=3, sleep=sleep, clock=clock) is None


def test_bootstrap_device_patches_bundle_and_builds(tmp_path: Path) -> None:
    project = _project_with_pbxproj(tmp_path)
    runner = RecordingRunner()
    service = BootstrapService(
        runner=runner,
        process_manager=FakeProcessManager(),
        project=project,
        state_dir=tmp_path,
    )
    service.bootstrap(signing=_SIGNING)

    assert "com.lazyworker.wda.Runner" in (project.project_path / "project.pbxproj").read_text()
    build_call = next(c for c in runner.calls if "build-for-testing" in c)
    assert "DEVELOPMENT_TEAM=92K8JB9444" in build_call


def test_up_device_orchestrates(tmp_path: Path) -> None:
    manager = FakeProcessManager()
    service = BootstrapService(
        runner=RecordingRunner(),
        process_manager=manager,
        project=_project(tmp_path),
        state_dir=tmp_path,
        sleep=lambda _: None,
    )

    state = service.up_device(
        "UDID", signing=_SIGNING, base_url="http://127.0.0.1:8100", port=8100, probe=lambda: True
    )

    assert state.kind == "device"
    assert state.pid == 4242
    assert state.forward_pid == 4243
    assert any("test-without-building" in c for c in manager.spawned)
    assert any("iproxy" in c for c in manager.spawned)
    assert load_run_state(tmp_path) == state


def test_up_device_network_mode_uses_advertised_url(tmp_path: Path) -> None:
    (tmp_path / "wda-device.log").write_text(
        "Running tests...\nServerURLHere->http://192.168.1.50:8100<-ServerURLHere\n"
    )
    manager = FakeProcessManager()
    service = BootstrapService(
        runner=RecordingRunner(),
        process_manager=manager,
        project=_project(tmp_path),
        state_dir=tmp_path,
        sleep=lambda _: None,
    )

    state = service.up_device(
        "UDID",
        signing=_SIGNING,
        base_url="http://127.0.0.1:8100",
        port=8100,
        connection="network",
        probe=lambda: True,
    )

    assert state.base_url == "http://192.168.1.50:8100"
    assert state.forward_pid is None
    assert not any("iproxy" in c for c in manager.spawned)
    assert any("test-without-building" in c for c in manager.spawned)


def test_up_device_timeout_terminates_both(tmp_path: Path) -> None:
    manager = FakeProcessManager()
    service = BootstrapService(
        runner=RecordingRunner(),
        process_manager=manager,
        project=_project(tmp_path),
        state_dir=tmp_path,
        sleep=lambda _: None,
    )

    with pytest.raises(BootstrapError):
        service.up_device(
            "UDID", signing=_SIGNING, base_url="http://x", port=8100, timeout=2, probe=lambda: False
        )

    assert set(manager.terminated) == {4242, 4243}
    assert load_run_state(tmp_path) is None


def test_subprocess_manager_terminates_real_process() -> None:
    manager = SubprocessProcessManager()
    process = manager.spawn(["sleep", "30"])
    assert process.is_running()
    manager.terminate(process.pid)
    for _ in range(60):
        if not process.is_running():
            break
        time.sleep(0.1)
    assert not process.is_running()


def test_up_resets_existing_state(tmp_path: Path) -> None:
    save_run_state(
        RunState(udid="OLD", port=8100, pid=111, base_url="http://x", kind="simulator"),
        tmp_path,
    )
    manager = FakeProcessManager()
    service = BootstrapService(
        runner=RecordingRunner(),
        process_manager=manager,
        project=_project(tmp_path),
        state_dir=tmp_path,
        sleep=lambda _: None,
    )
    state = service.up("U1", base_url="http://127.0.0.1:8100", port=8100, probe=lambda: True)
    assert 111 in manager.terminated
    assert state.udid == "U1"


def test_set_runner_bundle_id_raises_when_marker_absent(tmp_path: Path) -> None:
    project = _project(tmp_path)
    project.project_path.mkdir(parents=True)
    (project.project_path / "project.pbxproj").write_text("nothing relevant here\n")
    with pytest.raises(BootstrapError):
        WdaProvisioner(RecordingRunner(), project).set_runner_bundle_id("com.x.Runner")


def test_down_terminates_forward_then_pid(tmp_path: Path) -> None:
    manager = FakeProcessManager()
    service = BootstrapService(
        runner=RecordingRunner(),
        process_manager=manager,
        project=_project(tmp_path),
        state_dir=tmp_path,
    )
    save_run_state(
        RunState(udid="U", port=8100, pid=900, base_url="http://x", kind="device", forward_pid=901),
        tmp_path,
    )

    service.down()
    assert manager.terminated == [901, 900]
