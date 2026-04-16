from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..models.repo_map import RepoMap, RepoMapScan, RepoMapZone
from .file_classifier import FileClassifier, ScannedDirectory, ScannedFile
from .framework_detector import FrameworkDetector


@dataclass(frozen=True, slots=True)
class _ScanSnapshot:
    files: list[ScannedFile]
    directories: list[ScannedDirectory]
    scanned_directories: int
    scanned_files: int
    files_skipped: int
    directories_skipped: int
    truncated: bool


class RepoMapperError(ValueError):
    """Raised when a repository cannot be mapped safely."""


class RepoMapper:
    """Deterministic filesystem mapper for deriving a compact repo fingerprint."""

    def __init__(
        self,
        *,
        max_depth: int = 8,
        max_directories: int = 500,
        max_files: int = 3000,
        max_text_files: int = 120,
        max_read_bytes: int = 16384,
        max_matches_per_category: int = 8,
    ) -> None:
        self.max_depth = max_depth
        self.max_directories = max_directories
        self.max_files = max_files
        self.max_text_files = max_text_files
        self.max_read_bytes = max_read_bytes
        self.file_classifier = FileClassifier(max_matches_per_category=max_matches_per_category)
        self.framework_detector = FrameworkDetector()

    def map_repo(self, repo_path: str | Path) -> RepoMap:
        root = self._resolve_root(repo_path)
        snapshot = self._scan(root)
        text_snippets = self._load_text_snippets(snapshot.files)
        languages = self.file_classifier.detect_languages(snapshot.files)
        stacks = self.framework_detector.detect_frameworks(snapshot.files, text_snippets)
        package_managers = self.framework_detector.detect_package_managers(snapshot.files)
        unsupported_technologies = self.framework_detector.detect_unsupported_technologies(
            snapshot.files,
            text_snippets,
            package_managers=package_managers,
            detected_stacks=stacks,
        )
        key_files = self.file_classifier.build_key_files(snapshot.files, snapshot.directories, text_snippets)
        likely_entry_points = self.file_classifier.likely_entry_points(snapshot.files, text_snippets)
        top_folders = self.file_classifier.top_folders(snapshot.files)
        manual_review_zones = self._detect_manual_review_zones(snapshot.files, key_files, likely_entry_points)

        repo_map = RepoMap(
            repo_name=root.name,
            root_path=str(root),
            summary="",
            primary_stack=self._pick_primary_stack(stacks),
            languages=languages,
            stacks=stacks,
            package_managers=package_managers,
            key_files=key_files,
            likely_entry_points=likely_entry_points,
            unsupported_technologies=unsupported_technologies,
            needs_manual_review_zones=manual_review_zones,
            unsupported_zones=manual_review_zones,
            scan=RepoMapScan(
                scanned_directories=snapshot.scanned_directories,
                scanned_files=snapshot.scanned_files,
                files_skipped=snapshot.files_skipped,
                directories_skipped=snapshot.directories_skipped,
                truncated=snapshot.truncated,
                top_folders=top_folders,
            ),
        )
        repo_map.summary = self._build_summary(repo_map)
        return repo_map

    def _resolve_root(self, repo_path: str | Path) -> Path:
        root = Path(repo_path).expanduser().resolve(strict=False)
        if not root.exists():
            raise RepoMapperError(f"Repository path '{root}' does not exist.")
        if not root.is_dir():
            raise RepoMapperError(f"Repository path '{root}' is not a directory.")
        return root

    def _scan(self, root: Path) -> _ScanSnapshot:
        files: list[ScannedFile] = []
        directories: list[ScannedDirectory] = []
        scanned_directories = 0
        scanned_files = 0
        files_skipped = 0
        directories_skipped = 0
        truncated = False
        queue = deque([(root, 0)])

        while queue:
            current_dir, depth = queue.popleft()
            scanned_directories += 1
            if scanned_directories > self.max_directories:
                truncated = True
                break

            try:
                entries = sorted(current_dir.iterdir(), key=lambda entry: (entry.is_file(), entry.name.lower()))
            except OSError:
                directories_skipped += 1
                continue

            for entry in entries:
                if entry.is_symlink():
                    if entry.is_file():
                        files_skipped += 1
                    elif entry.is_dir():
                        directories_skipped += 1
                    continue

                if entry.is_dir():
                    if self.file_classifier.is_ignored_directory(entry.name):
                        directories_skipped += 1
                        continue

                    relative_parts = entry.relative_to(root).parts
                    parts_lower = tuple(part.lower() for part in relative_parts)
                    relative_path = entry.relative_to(root).as_posix()
                    directories.append(
                        ScannedDirectory(
                            absolute_path=entry,
                            relative_path=relative_path,
                            name=entry.name,
                            depth=len(parts_lower) - 1,
                            lower_path=relative_path.lower(),
                            parts_lower=parts_lower,
                        )
                    )

                    if depth < self.max_depth:
                        queue.append((entry, depth + 1))
                    else:
                        directories_skipped += 1
                        truncated = True
                    continue

                if not entry.is_file():
                    files_skipped += 1
                    continue

                scanned_files += 1
                if scanned_files > self.max_files:
                    files_skipped += 1
                    truncated = True
                    break

                relative_path = entry.relative_to(root).as_posix()
                relative_parts = entry.relative_to(root).parts
                parts_lower = tuple(part.lower() for part in relative_parts)
                files.append(
                    ScannedFile(
                        absolute_path=entry,
                        relative_path=relative_path,
                        name=entry.name,
                        depth=len(parts_lower) - 1,
                        suffix=entry.suffix.lower(),
                        lower_path=relative_path.lower(),
                        lower_name=entry.name.lower(),
                        parts_lower=parts_lower,
                    )
                )

            if truncated:
                break

        files.sort(key=lambda item: (item.depth, item.relative_path))
        directories.sort(key=lambda item: (item.depth, item.relative_path))
        return _ScanSnapshot(
            files=files,
            directories=directories,
            scanned_directories=min(scanned_directories, self.max_directories),
            scanned_files=min(scanned_files, self.max_files),
            files_skipped=files_skipped,
            directories_skipped=directories_skipped,
            truncated=truncated,
        )

    def _load_text_snippets(self, files: list[ScannedFile]) -> dict[str, str]:
        candidates: list[ScannedFile] = []
        interesting_parts = {
            "api",
            "app",
            "src",
            "server",
            "backend",
            "routes",
            "auth",
            "db",
            "prisma",
            "supabase",
            "validation",
            "validator",
            "schema",
            "schemas",
            "middleware",
            "webhook",
            "webhooks",
            "frontend",
            "client",
            "components",
            "hooks",
        }
        for file in files:
            if not self.file_classifier.is_text_candidate(file):
                continue
            if self._should_skip_text_scan(file):
                continue
            if file.depth > 4 and not any(part in interesting_parts for part in file.parts_lower):
                continue
            candidates.append(file)

        candidates.sort(
            key=lambda file: (
                not any(part in interesting_parts for part in file.parts_lower),
                file.depth,
                file.relative_path,
            )
        )

        snippets: dict[str, str] = {}
        for file in candidates[: self.max_text_files]:
            text = self._read_text_prefix(file.absolute_path)
            if text is None:
                continue
            snippets[file.relative_path] = text.lower()
        return snippets

    def _should_skip_text_scan(self, file: ScannedFile) -> bool:
        excluded_parts = {"tests", "test", "docs", "examples"}
        return any(part in excluded_parts for part in file.parts_lower[:-1])

    def _read_text_prefix(self, path: Path) -> str | None:
        try:
            with path.open("rb") as handle:
                chunk = handle.read(self.max_read_bytes)
        except OSError:
            return None
        return chunk.decode("utf-8", errors="ignore")

    def _detect_manual_review_zones(
        self,
        files: list[ScannedFile],
        key_files,
        likely_entry_points,
    ) -> list[RepoMapZone]:
        signal_paths = {
            item.path
            for group in (
                key_files.routes,
                key_files.auth,
                key_files.database,
                key_files.middleware,
                key_files.validation,
                key_files.webhooks,
                key_files.frontend,
                key_files.env,
                key_files.config,
                key_files.manifests,
                key_files.lockfiles,
                key_files.infra,
                key_files.ai_rules,
                likely_entry_points,
            )
            for item in group
        }

        folder_counts: dict[str, int] = {}
        folder_signal_counts: dict[str, int] = {}
        for file in files:
            parts = PurePosixPath(file.relative_path).parts
            top_folder = parts[0] if len(parts) > 1 else "."
            folder_counts[top_folder] = folder_counts.get(top_folder, 0) + 1
            if file.relative_path in signal_paths:
                folder_signal_counts[top_folder] = folder_signal_counts.get(top_folder, 0) + 1

        ignored_unknowns = {".", "docs", "tests", "test", "scripts", "examples"}
        zones: list[RepoMapZone] = []
        for folder, file_count in sorted(folder_counts.items(), key=lambda item: (-item[1], item[0])):
            if folder in ignored_unknowns or file_count < 3:
                continue
            if folder_signal_counts.get(folder, 0) > 0:
                continue
            zones.append(
                RepoMapZone(
                    path=folder,
                    reason="scanned folder with weak or no route/config/framework signals and may need manual review",
                )
            )
            if len(zones) >= 6:
                break
        return zones

    def _pick_primary_stack(self, stacks) -> str | None:
        preferred_categories = ("framework", "platform", "runtime")
        for category in preferred_categories:
            for stack in stacks:
                if stack.category == category:
                    return stack.slug
        return stacks[0].slug if stacks else None

    def _build_summary(self, repo_map: RepoMap) -> str:
        languages = ", ".join(repo_map.languages) if repo_map.languages else "unknown language"
        stack_names = ", ".join(stack.name for stack in repo_map.stacks[:3]) or "no clear framework"
        manager_names = ", ".join(manager.name for manager in repo_map.package_managers[:3]) or "unknown package manager"
        route_count = len(repo_map.key_files.routes)
        auth_count = len(repo_map.key_files.auth)
        database_count = len(repo_map.key_files.database)
        webhook_count = len(repo_map.key_files.webhooks)
        validation_count = len(repo_map.key_files.validation)
        middleware_count = len(repo_map.key_files.middleware)
        unsupported_technology_count = len(repo_map.unsupported_technologies)
        manual_review_zone_count = len(repo_map.needs_manual_review_zones)
        truncated = " Scan was truncated for speed." if repo_map.scan.truncated else ""
        support_suffix = ""
        if unsupported_technology_count or manual_review_zone_count:
            support_suffix = (
                f" Marked {unsupported_technology_count} unsupported technolog"
                f"{'y' if unsupported_technology_count == 1 else 'ies'} and "
                f"{manual_review_zone_count} manual-review zone"
                f"{'' if manual_review_zone_count == 1 else 's'}."
            )
        return (
            f"Detected {languages} repo with {stack_names}. "
            f"Package managers: {manager_names}. "
            f"Found {route_count} API routes, {auth_count} auth/session files, "
            f"{database_count} database files, {validation_count} validation files, "
            f"{middleware_count} middleware files, and {webhook_count} webhook files."
            f"{support_suffix}{truncated}"
        )
