from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lazyworker.bootstrap.errors import BootstrapError
from lazyworker.bootstrap.process import ManagedProcess, ProcessManager
from lazyworker.devices.runner import CommandRunner

WDA_REPOSITORY = "https://github.com/appium/WebDriverAgent.git"
WDA_SCHEME = "WebDriverAgentRunner"
SIMULATOR_DESTINATION = "generic/platform=iOS Simulator"
DEVICE_DESTINATION = "generic/platform=iOS"
DEFAULT_RUNNER_BUNDLE_ID = "com.facebook.WebDriverAgentRunner"

CLONE_TIMEOUT = 600.0
BUILD_TIMEOUT = 1800.0


@dataclass
class SigningOptions:
    """Signing parameters for a physical-device build."""

    team_id: str
    runner_bundle_id: str


@dataclass
class WdaProject:
    """Filesystem locations for the WebDriverAgent source and build output."""

    source_dir: Path
    derived_data_dir: Path
    repository: str = WDA_REPOSITORY
    ref: str | None = None

    @property
    def project_path(self) -> Path:
        return self.source_dir / "WebDriverAgent.xcodeproj"

    @property
    def products_dir(self) -> Path:
        return self.derived_data_dir / "Build" / "Products"

    def is_present(self) -> bool:
        return self.project_path.exists()

    def has_build(self) -> bool:
        return self.products_dir.exists() and any(self.products_dir.glob("*/*.app"))


class WdaProvisioner:
    """Ensures the WebDriverAgent source is available locally."""

    def __init__(self, runner: CommandRunner, project: WdaProject) -> None:
        self._runner = runner
        self._project = project

    def ensure_source(self) -> None:
        if self._project.is_present():
            return
        self._project.source_dir.parent.mkdir(parents=True, exist_ok=True)
        args = ["git", "clone", "--depth", "1"]
        if self._project.ref:
            args += ["--branch", self._project.ref]
        args += [self._project.repository, str(self._project.source_dir)]
        self._runner.run(args, timeout=CLONE_TIMEOUT)

    def set_runner_bundle_id(self, bundle_id: str) -> None:
        """Rewrite the runner's bundle id so a free account can sign it (idempotent)."""
        pbxproj = self._project.project_path / "project.pbxproj"
        text = pbxproj.read_text()
        target = f"PRODUCT_BUNDLE_IDENTIFIER = {bundle_id};"
        if target in text:
            return
        marker = f"PRODUCT_BUNDLE_IDENTIFIER = {DEFAULT_RUNNER_BUNDLE_ID};"
        if marker not in text:
            raise BootstrapError(
                "Could not find the WebDriverAgentRunner bundle id in the project; "
                "the WebDriverAgent layout may have changed."
            )
        pbxproj.write_text(text.replace(marker, target))


class WdaBuilder:
    """Builds WebDriverAgent for the simulator (no code signing)."""

    def __init__(self, runner: CommandRunner, project: WdaProject) -> None:
        self._runner = runner
        self._project = project

    def build_for_testing(self) -> None:
        self._runner.run(
            [
                "xcodebuild",
                "build-for-testing",
                "-project",
                str(self._project.project_path),
                "-scheme",
                WDA_SCHEME,
                "-destination",
                SIMULATOR_DESTINATION,
                "-derivedDataPath",
                str(self._project.derived_data_dir),
                "CODE_SIGNING_ALLOWED=NO",
            ],
            timeout=BUILD_TIMEOUT,
        )

    def build_device(self, signing: SigningOptions) -> None:
        self._runner.run(
            [
                "xcodebuild",
                "build-for-testing",
                "-project",
                str(self._project.project_path),
                "-scheme",
                WDA_SCHEME,
                "-destination",
                DEVICE_DESTINATION,
                "-derivedDataPath",
                str(self._project.derived_data_dir),
                "-allowProvisioningUpdates",
                f"DEVELOPMENT_TEAM={signing.team_id}",
                "CODE_SIGN_STYLE=Automatic",
            ],
            timeout=BUILD_TIMEOUT,
        )


class WdaLauncher:
    """Launches the WebDriverAgent test runner on a booted simulator."""

    def __init__(self, process_manager: ProcessManager, project: WdaProject) -> None:
        self._process_manager = process_manager
        self._project = project

    def launch(self, udid: str, *, log_path: Path | None = None) -> ManagedProcess:
        return self._process_manager.spawn(
            [
                "xcodebuild",
                "test-without-building",
                "-project",
                str(self._project.project_path),
                "-scheme",
                WDA_SCHEME,
                "-destination",
                f"platform=iOS Simulator,id={udid}",
                "-derivedDataPath",
                str(self._project.derived_data_dir),
                "CODE_SIGNING_ALLOWED=NO",
            ],
            log_path=log_path,
        )

    def launch_device(
        self, udid: str, signing: SigningOptions, *, log_path: Path | None = None
    ) -> ManagedProcess:
        return self._process_manager.spawn(
            [
                "xcodebuild",
                "test-without-building",
                "-project",
                str(self._project.project_path),
                "-scheme",
                WDA_SCHEME,
                "-destination",
                f"platform=iOS,id={udid}",
                "-derivedDataPath",
                str(self._project.derived_data_dir),
                "-allowProvisioningUpdates",
                f"DEVELOPMENT_TEAM={signing.team_id}",
            ],
            log_path=log_path,
        )
