"""
=============================================================
Human-Paced Computing v0.2
=============================================================

Research prototype for studying human-paced computer behavior.

WHAT IT DOES
------------
1. Asks for a source/parent folder.
2. Recursively finds supported text/code files.
3. Randomizes file order.
4. Uses the current working directory as the destination.
5. Recreates the source folder structure.
6. Opens generated files in VS Code when possible.
7. Progressively writes the correct source contents.
8. Uses a stateful dynamic Words-Per-Second (WPS) model.
9. Introduces research-only "revision episodes".
10. Records pacing and revision behavior into CSV logs.
11. Displays live model/current/average WPS.

REVISION MODEL
--------------
Revision presets represent cognitive/review events such as:

    - reconsidering a variable name
    - checking error handling
    - reconsidering a branch
    - reviewing a helper function
    - checking an edge case

These are NOT inserted into the real destination file.

Instead:

    writing
       ↓
    revision event
       ↓
    temporary internal research state
       ↓
    pause
       ↓
    resume correct writing

This lets the thesis study revision behavior without creating
fake project history.

RUN
---
    python test.py
"""

from __future__ import annotations

import csv
import random
import shutil
import subprocess
import sys
import time

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# ============================================================
# Application
# ============================================================

APP_NAME = "Human-Paced Computing"
VERSION = "v0.2"


# ============================================================
# Pacing configuration
# ============================================================

MIN_WPS = 2.0
MAX_WPS = 5.0

CHARS_PER_WORD = 5.0

PROGRESS_INTERVAL = 100


# ============================================================
# Revision configuration
# ============================================================

# Probability evaluated at eligible boundaries.
REVISION_PROBABILITY = 0.045

# Minimum amount of content between revision opportunities.
MIN_CHARS_BETWEEN_REVISIONS = 250

# Research-only pause duration.
REVISION_PAUSE_MIN = 1.0
REVISION_PAUSE_MAX = 5.0


# ============================================================
# Supported files
# ============================================================

TEXT_EXTENSIONS = {
    ".txt",
    ".md",

    # Python
    ".py",

    # JavaScript / TypeScript
    ".js",
    ".jsx",
    ".ts",
    ".tsx",

    # Web
    ".html",
    ".css",
    ".scss",

    # Data/config
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".toml",
    ".ini",
    ".env",

    # Other
    ".sql",
    ".sh",
    ".bat",
    ".ps1",
    ".csv",
}


# ============================================================
# Ignored directories
# ============================================================

IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",

    "node_modules",

    "__pycache__",

    ".venv",
    "venv",

    "dist",
    "build",

    ".next",
    ".cache",

    ".idea",
    ".vscode",
}


# ============================================================
# Revision presets
# ============================================================

REVISION_PRESETS = [
    {
        "name": "review_variable_name",
        "description": "Reconsider whether a variable name is clear enough.",
    },
    {
        "name": "review_function_name",
        "description": "Check whether the function name communicates its purpose.",
    },
    {
        "name": "review_error_handling",
        "description": "Check whether an error path is handled correctly.",
    },
    {
        "name": "review_edge_case",
        "description": "Consider an unusual or boundary input.",
    },
    {
        "name": "review_condition",
        "description": "Reconsider whether a conditional branch is correct.",
    },
    {
        "name": "review_return_value",
        "description": "Check whether the function returns the intended value.",
    },
    {
        "name": "review_loop",
        "description": "Reconsider loop behavior and termination.",
    },
    {
        "name": "review_imports",
        "description": "Check whether imports are necessary and consistent.",
    },
    {
        "name": "review_structure",
        "description": "Reconsider the structure of the surrounding code.",
    },
    {
        "name": "review_duplication",
        "description": "Look for duplicated logic that could be simplified.",
    },
    {
        "name": "review_boundary",
        "description": "Check behavior at a boundary value.",
    },
    {
        "name": "review_null_case",
        "description": "Check how missing or empty values are handled.",
    },
    {
        "name": "review_type_consistency",
        "description": "Check whether values have consistent types.",
    },
    {
        "name": "review_readability",
        "description": "Pause and reconsider whether the current section is readable.",
    },
    {
        "name": "review_complexity",
        "description": "Consider whether the current logic is unnecessarily complex.",
    },
    {
        "name": "review_dependency",
        "description": "Consider whether the current dependency is actually needed.",
    },
    {
        "name": "review_api_usage",
        "description": "Check whether an external API call is being used correctly.",
    },
    {
        "name": "review_state",
        "description": "Reconsider how state changes through this section.",
    },
    {
        "name": "review_data_flow",
        "description": "Trace where the current data comes from and where it goes.",
    },
    {
        "name": "review_security",
        "description": "Pause and consider whether the implementation exposes an unsafe assumption.",
    },
    {
        "name": "review_performance",
        "description": "Consider whether the current operation could become expensive.",
    },
    {
        "name": "review_cleanup",
        "description": "Check whether temporary resources are properly cleaned up.",
    },
    {
        "name": "review_testability",
        "description": "Consider whether this section is straightforward to test.",
    },
    {
        "name": "review_documentation",
        "description": "Consider whether the intent of this section is clear.",
    },
    {
        "name": "review_final_consistency",
        "description": "Check whether the new section remains consistent with the surrounding code.",
    },
]


# ============================================================
# Data models
# ============================================================

@dataclass
class PacingState:
    """State of the writing pace."""

    wps: float
    fatigue: float = 0.0
    momentum: float = 0.0


@dataclass
class RevisionState:
    """State of revision opportunities for one file."""

    last_revision_index: int = 0
    revision_count: int = 0


@dataclass
class SessionStats:
    """Statistics for the complete session."""

    files_total: int = 0
    files_completed: int = 0
    files_skipped: int = 0

    total_words: int = 0
    total_characters: int = 0

    start_time: float = 0.0

    total_writing_time: float = 0.0
    total_revision_time: float = 0.0

    model_wps_sum: float = 0.0
    model_wps_samples: int = 0

    revisions_total: int = 0

    @property
    def average_wps(self) -> float:
        """
        Overall observed writing WPS.

        Revision pauses are excluded from writing time.
        """

        if self.total_writing_time <= 0:
            return 0.0

        if self.total_words <= 0:
            return 0.0

        return self.total_words / self.total_writing_time

    @property
    def average_model_wps(self) -> float:
        """Average model WPS."""

        if self.model_wps_samples <= 0:
            return 0.0

        return (
            self.model_wps_sum
            / self.model_wps_samples
        )


# ============================================================
# Utility
# ============================================================

def normalize_path(value: str) -> Path:
    """Normalize a user-entered path."""

    return (
        Path(
            value.strip().strip('"')
        )
        .expanduser()
        .resolve()
    )


def count_words(text: str) -> int:
    """Simple whitespace-based word count."""

    return len(text.split())


def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    """Clamp value between two boundaries."""

    return max(
        minimum,
        min(maximum, value),
    )


def format_duration(seconds: float) -> str:
    """Format seconds as readable duration."""

    seconds = max(
        0,
        int(seconds),
    )

    hours, remainder = divmod(
        seconds,
        3600,
    )

    minutes, seconds = divmod(
        remainder,
        60,
    )

    if hours:
        return (
            f"{hours}h "
            f"{minutes}m "
            f"{seconds}s"
        )

    if minutes:
        return (
            f"{minutes}m "
            f"{seconds}s"
        )

    return f"{seconds}s"


# ============================================================
# VS Code
# ============================================================

def vscode_available() -> bool:
    """Return whether the VS Code CLI exists."""

    return shutil.which("code") is not None


def open_in_vscode(path: Path) -> None:
    """Ask VS Code to open a file."""

    if not vscode_available():
        return

    try:

        subprocess.Popen(
            [
                "code",
                "--reuse-window",
                str(path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    except (
        OSError,
        subprocess.SubprocessError,
    ):
        pass


# ============================================================
# File discovery
# ============================================================

def should_ignore(path: Path) -> bool:
    """Check whether a path belongs to an ignored directory."""

    return any(
        part in IGNORED_DIRECTORIES
        for part in path.parts
    )


def is_supported_file(path: Path) -> bool:
    """Check whether the file is supported."""

    return (
        path.is_file()
        and path.suffix.lower()
        in TEXT_EXTENSIONS
    )


def find_files(parent: Path) -> list[Path]:
    """Recursively find supported files."""

    files: list[Path] = []

    for path in parent.rglob("*"):

        if should_ignore(path):
            continue

        if is_supported_file(path):
            files.append(path)

    files.sort()

    return files


# ============================================================
# Pacing model
# ============================================================

def update_pacing(
    state: PacingState,
    char: str,
) -> float:
    """
    Update stateful writing pace.

    This is an experimental model, not a validated model
    of actual human typing behavior.
    """

    # Slow natural drift.
    state.momentum += random.uniform(
        -0.10,
        0.10,
    )

    state.momentum *= 0.90

    # Mild fatigue.
    state.fatigue += 0.000015

    # Apply state.
    state.wps += state.momentum
    state.wps -= state.fatigue

    # Structural context.
    if char in ".!?":

        state.wps -= random.uniform(
            0.15,
            0.50,
        )

    elif char in ",;:":

        state.wps -= random.uniform(
            0.05,
            0.20,
        )

    elif char == "\n":

        state.wps -= random.uniform(
            0.10,
            0.35,
        )

    # Keep pace within experimental range.
    state.wps = clamp(
        state.wps,
        MIN_WPS,
        MAX_WPS,
    )

    return state.wps


def calculate_delay(
    state: PacingState,
    char: str,
) -> tuple[float, float]:
    """Calculate character delay and current WPS."""

    model_wps = update_pacing(
        state,
        char,
    )

    characters_per_second = (
        model_wps
        * CHARS_PER_WORD
    )

    delay = (
        1.0
        / characters_per_second
    )

    # Small variability.
    delay *= random.uniform(
        0.85,
        1.15,
    )

    # Contextual pauses.
    if char in ".!?":

        delay += random.uniform(
            0.20,
            0.75,
        )

    elif char in ",;:":

        delay += random.uniform(
            0.08,
            0.30,
        )

    elif char == "\n":

        delay += random.uniform(
            0.15,
            0.50,
        )

    elif char == " ":

        delay += random.uniform(
            0.005,
            0.04,
        )

    return delay, model_wps


# ============================================================
# Revision model
# ============================================================

def choose_revision_preset() -> dict[str, str]:
    """Choose one research revision preset."""

    return random.choice(
        REVISION_PRESETS
    )


def revision_is_eligible(
    content: str,
    index: int,
    revision_state: RevisionState,
) -> bool:
    """
    Determine whether the current position is eligible
    for a revision event.
    """

    if index <= 0:
        return False

    if (
        index
        - revision_state.last_revision_index
        < MIN_CHARS_BETWEEN_REVISIONS
    ):
        return False

    # Prefer boundaries where a person could naturally stop:
    # whitespace, newline, punctuation.
    current = content[index - 1]

    if current not in {
        " ",
        "\n",
        ".",
        ",",
        ";",
        ":",
        "!",
        "?",
    }:
        return False

    return (
        random.random()
        < REVISION_PROBABILITY
    )


def perform_revision_episode(
    content: str,
    index: int,
    revision_state: RevisionState,
    stats: SessionStats,
    revision_writer,
    revision_state_writer,
    destination: Path,
    model_wps: float,
) -> None:
    """
    Perform a research-only revision episode.

    No decoy text is inserted into the destination file.

    The event exists in the model/log and the correct source
    content continues afterward.
    """

    preset = choose_revision_preset()

    revision_state.last_revision_index = index
    revision_state.revision_count += 1

    stats.revisions_total += 1

    started = time.perf_counter()

    start_timestamp = datetime.now()

    pause = random.uniform(
        REVISION_PAUSE_MIN,
        REVISION_PAUSE_MAX,
    )

    # --------------------------------------------------------
    # Terminal
    # --------------------------------------------------------

    print()
    print(
        "      [REVISION]"
    )
    print(
        f"      preset  : "
        f"{preset['name']}"
    )
    print(
        f"      thought : "
        f"{preset['description']}"
    )
    print(
        f"      pause   : "
        f"{pause:.2f}s"
    )

    # --------------------------------------------------------
    # Research event
    # --------------------------------------------------------

    revision_writer.writerow(
        [
            start_timestamp.isoformat(
                timespec="milliseconds"
            ),
            str(destination),
            index,
            revision_state.revision_count,
            preset["name"],
            preset["description"],
            f"{model_wps:.4f}",
            f"{pause:.4f}",
            "started",
        ]
    )

    revision_state_writer.writerow(
        [
            start_timestamp.isoformat(
                timespec="milliseconds"
            ),
            str(destination),
            index,
            preset["name"],
            "revision_started",
        ]
    )

    # --------------------------------------------------------
    # Temporary internal state
    # --------------------------------------------------------

    # This is deliberately NOT written to the destination.
    #
    # The system simply represents that the model is
    # reconsidering its previous decision.
    #
    # We keep the selected preset alive during the pause,
    # then discard the state.

    active_revision = {
        "preset": preset["name"],
        "description": preset["description"],
        "position": index,
    }

    _ = active_revision

    time.sleep(
        pause
    )

    elapsed = (
        time.perf_counter()
        - started
    )

    stats.total_revision_time += elapsed

    end_timestamp = datetime.now()

    revision_writer.writerow(
        [
            end_timestamp.isoformat(
                timespec="milliseconds"
            ),
            str(destination),
            index,
            revision_state.revision_count,
            preset["name"],
            preset["description"],
            f"{model_wps:.4f}",
            f"{elapsed:.4f}",
            "completed",
        ]
    )

    revision_state_writer.writerow(
        [
            end_timestamp.isoformat(
                timespec="milliseconds"
            ),
            str(destination),
            index,
            preset["name"],
            "revision_completed",
        ]
    )

    print(
        "      [RESUME]"
    )
    print()


# ============================================================
# Logging
# ============================================================

def create_log_folder(
    destination_root: Path,
) -> Path:
    """Create a session folder."""

    timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    log_folder = (
        destination_root
        / ".hpc"
        / "sessions"
        / timestamp
    )

    log_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    return log_folder


def create_event_logger(
    log_folder: Path,
):
    """Create character-level event log."""

    path = (
        log_folder
        / "events.csv"
    )

    handle = path.open(
        "w",
        newline="",
        encoding="utf-8",
    )

    writer = csv.writer(
        handle
    )

    writer.writerow(
        [
            "timestamp",
            "file",
            "character_index",
            "model_wps",
            "delay_seconds",
            "character_type",
        ]
    )

    return handle, writer


def create_file_logger(
    log_folder: Path,
):
    """Create file-level log."""

    path = (
        log_folder
        / "files.csv"
    )

    handle = path.open(
        "w",
        newline="",
        encoding="utf-8",
    )

    writer = csv.writer(
        handle
    )

    writer.writerow(
        [
            "file",
            "characters",
            "words",
            "duration_seconds",
            "observed_wps",
            "revision_count",
            "status",
        ]
    )

    return handle, writer


def create_revision_logger(
    log_folder: Path,
):
    """Create revision-event log."""

    path = (
        log_folder
        / "revisions.csv"
    )

    handle = path.open(
        "w",
        newline="",
        encoding="utf-8",
    )

    writer = csv.writer(
        handle
    )

    writer.writerow(
        [
            "timestamp",
            "file",
            "character_index",
            "revision_number",
            "preset",
            "description",
            "model_wps",
            "duration_or_pause",
            "status",
        ]
    )

    return handle, writer


def create_revision_state_logger(
    log_folder: Path,
):
    """Create a compact revision state log."""

    path = (
        log_folder
        / "revision_state.csv"
    )

    handle = path.open(
        "w",
        newline="",
        encoding="utf-8",
    )

    writer = csv.writer(
        handle
    )

    writer.writerow(
        [
            "timestamp",
            "file",
            "character_index",
            "preset",
            "state",
        ]
    )

    return handle, writer


# ============================================================
# Progressive writer
# ============================================================

def write_file(
    source: Path,
    destination: Path,
    stats: SessionStats,
    event_writer,
    revision_writer,
    revision_state_writer,
    file_writer,
) -> bool:
    """Progressively write one source file."""

    # --------------------------------------------------------
    # Read
    # --------------------------------------------------------

    try:

        content = source.read_text(
            encoding="utf-8"
        )

    except UnicodeDecodeError:

        print(
            f"\n  [SKIP] "
            f"UTF-8 decoding failed: {source}"
        )

        return False

    except OSError as exc:

        print(
            f"\n  [SKIP] "
            f"Could not read file: {exc}"
        )

        return False

    # --------------------------------------------------------
    # Destination
    # --------------------------------------------------------

    try:

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination.write_text(
            "",
            encoding="utf-8",
        )

    except OSError as exc:

        print(
            f"\n  [SKIP] "
            f"Could not create destination: {exc}"
        )

        return False

    # Open in VS Code.
    open_in_vscode(
        destination
    )

    time.sleep(
        0.4
    )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    word_count = count_words(
        content
    )

    character_count = len(
        content
    )

    stats.total_words += word_count
    stats.total_characters += character_count

    # Empty file.
    if not content:

        file_writer.writerow(
            [
                str(destination),
                0,
                0,
                0,
                0,
                0,
                "completed",
            ]
        )

        return True

    # --------------------------------------------------------
    # State
    # --------------------------------------------------------

    pacing_state = PacingState(
        wps=random.uniform(
            MIN_WPS,
            MAX_WPS,
        )
    )

    revision_state = RevisionState()

    file_start = time.perf_counter()

    # --------------------------------------------------------
    # Write
    # --------------------------------------------------------

    try:

        with destination.open(
            "w",
            encoding="utf-8",
        ) as output:

            for index, char in enumerate(
                content,
                start=1,
            ):

                # --------------------------------------------
                # Calculate pacing
                # --------------------------------------------

                (
                    delay,
                    model_wps,
                ) = calculate_delay(
                    pacing_state,
                    char,
                )

                stats.model_wps_sum += (
                    model_wps
                )

                stats.model_wps_samples += 1

                # --------------------------------------------
                # Correct content is written
                # --------------------------------------------

                output.write(
                    char
                )

                output.flush()

                # --------------------------------------------
                # Delay
                # --------------------------------------------

                if index < character_count:

                    time.sleep(
                        delay
                    )

                # --------------------------------------------
                # Character category
                # --------------------------------------------

                if char == "\n":

                    character_type = (
                        "newline"
                    )

                elif char == " ":

                    character_type = (
                        "space"
                    )

                elif char in (
                    ".",
                    ",",
                    ";",
                    ":",
                    "!",
                    "?",
                ):

                    character_type = (
                        "punctuation"
                    )

                else:

                    character_type = (
                        "character"
                    )

                # --------------------------------------------
                # Event log
                # --------------------------------------------

                event_writer.writerow(
                    [
                        datetime.now().isoformat(
                            timespec="milliseconds"
                        ),
                        str(destination),
                        index,
                        f"{model_wps:.4f}",
                        f"{delay:.4f}",
                        character_type,
                    ]
                )

                # --------------------------------------------
                # Revision opportunity
                # --------------------------------------------

                if revision_is_eligible(
                    content,
                    index,
                    revision_state,
                ):

                    perform_revision_episode(
                        content=content,
                        index=index,
                        revision_state=revision_state,
                        stats=stats,
                        revision_writer=revision_writer,
                        revision_state_writer=revision_state_writer,
                        destination=destination,
                        model_wps=model_wps,
                    )

                # --------------------------------------------
                # Live metrics
                # --------------------------------------------

                elapsed = (
                    time.perf_counter()
                    - file_start
                )

                written_words = count_words(
                    content[:index]
                )

                current_wps = (
                    written_words / elapsed
                    if (
                        elapsed > 0
                        and written_words > 0
                    )
                    else 0.0
                )

                current_total_time = (
                    stats.total_writing_time
                    + elapsed
                )

                current_total_words = (
                    stats.total_words
                    - word_count
                    + written_words
                )

                average_wps = (
                    current_total_words
                    / current_total_time
                    if (
                        current_total_time > 0
                        and current_total_words > 0
                    )
                    else 0.0
                )

                # --------------------------------------------
                # Progress UI
                # --------------------------------------------

                if (
                    index % PROGRESS_INTERVAL == 0
                    or index == character_count
                ):

                    percentage = (
                        index
                        / character_count
                        * 100
                    )

                    print(
                        f"\r"
                        f"      {percentage:6.2f}% "
                        f"| "
                        f"{written_words}/{word_count} words "
                        f"| "
                        f"model {model_wps:4.2f} WPS "
                        f"| "
                        f"current {current_wps:4.2f} WPS "
                        f"| "
                        f"avg {average_wps:4.2f} WPS "
                        f"| "
                        f"revisions {revision_state.revision_count}",
                        end="",
                        flush=True,
                    )

    except KeyboardInterrupt:

        print(
            "\n\n  [STOPPED]"
        )

        raise

    except OSError as exc:

        print(
            f"\n  [ERROR] "
            f"Writing failed: {exc}"
        )

        return False

    # --------------------------------------------------------
    # File completed
    # --------------------------------------------------------

    duration = (
        time.perf_counter()
        - file_start
    )

    observed_wps = (
        word_count / duration
        if (
            duration > 0
            and word_count > 0
        )
        else 0.0
    )

    stats.total_writing_time += (
        duration
    )

    file_writer.writerow(
        [
            str(destination),
            character_count,
            word_count,
            f"{duration:.3f}",
            f"{observed_wps:.4f}",
            revision_state.revision_count,
            "completed",
        ]
    )

    print()

    return True


# ============================================================
# Overwrite prompt
# ============================================================

def ask_overwrite() -> bool:
    """Ask whether existing files may be overwritten."""

    while True:

        answer = input(
            "Some destination files already exist. "
            "Overwrite them? [y/N]: "
        ).strip().lower()

        if answer in {
            "y",
            "yes",
        }:

            return True

        if answer in {
            "",
            "n",
            "no",
        }:

            return False

        print(
            "Please enter y or n."
        )


# ============================================================
# UI
# ============================================================

def print_header() -> None:

    print()
    print("=" * 76)
    print(
        f"  {APP_NAME} {VERSION}"
    )
    print(
        "  Human-paced file evolution experiment"
    )
    print("=" * 76)
    print()


def print_summary(
    source_root: Path,
    destination_root: Path,
    files: list[Path],
) -> None:

    print()
    print("-" * 76)
    print("SESSION")
    print("-" * 76)

    print(
        f"Source      : {source_root}"
    )

    print(
        f"Destination : {destination_root}"
    )

    print(
        f"Files found : {len(files)}"
    )

    print(
        f"WPS range   : "
        f"{MIN_WPS:.1f} - {MAX_WPS:.1f}"
    )

    print(
        f"Revision probability: "
        f"{REVISION_PROBABILITY * 100:.1f}%"
    )

    print()


# ============================================================
# Main
# ============================================================

def main() -> None:

    print_header()

    # --------------------------------------------------------
    # Source folder
    # --------------------------------------------------------

    while True:

        raw_source = input(
            "Parent/source folder:\n> "
        ).strip()

        if not raw_source:

            print(
                "\nPlease enter a folder path.\n"
            )

            continue

        source_root = normalize_path(
            raw_source
        )

        if not source_root.exists():

            print(
                "\nThat folder does not exist.\n"
            )

            continue

        if not source_root.is_dir():

            print(
                "\nThat path is not a folder.\n"
            )

            continue

        break

    # --------------------------------------------------------
    # Destination
    # --------------------------------------------------------

    destination_root = (
        Path.cwd().resolve()
    )

    try:

        if (
            destination_root == source_root
            or destination_root.is_relative_to(
                source_root
            )
        ):

            print()
            print(
                "[ERROR] The current workspace "
                "is inside the source folder."
            )

            print(
                "Choose a source outside the workspace."
            )

            sys.exit(1)

    except ValueError:

        # Different Windows drives.
        pass

    # --------------------------------------------------------
    # Discovery
    # --------------------------------------------------------

    print()
    print(
        "Searching for files..."
    )

    files = find_files(
        source_root
    )

    if not files:

        print()
        print(
            "No supported text/code files found."
        )

        return

    random.shuffle(
        files
    )

    print_summary(
        source_root,
        destination_root,
        files,
    )

    # --------------------------------------------------------
    # File list
    # --------------------------------------------------------

    print(
        "Random processing order:"
    )

    print()

    for number, source_file in enumerate(
        files,
        start=1,
    ):

        relative = (
            source_file
            .relative_to(
                source_root
            )
        )

        print(
            f"  {number:03d}  {relative}"
        )

    print()

    # --------------------------------------------------------
    # Existing files
    # --------------------------------------------------------

    has_existing = any(
        (
            destination_root
            / file.relative_to(
                source_root
            )
        ).exists()
        for file in files
    )

    overwrite = True

    if has_existing:

        overwrite = ask_overwrite()

    # --------------------------------------------------------
    # Start
    # --------------------------------------------------------

    print()
    print(
        "-" * 76
    )

    input(
        "Press ENTER to start..."
    )

    print()

    # --------------------------------------------------------
    # Logs
    # --------------------------------------------------------

    log_folder = create_log_folder(
        destination_root
    )

    event_handle, event_writer = (
        create_event_logger(
            log_folder
        )
    )

    file_handle, file_writer = (
        create_file_logger(
            log_folder
        )
    )

    revision_handle, revision_writer = (
        create_revision_logger(
            log_folder
        )
    )

    revision_state_handle, revision_state_writer = (
        create_revision_state_logger(
            log_folder
        )
    )

    stats = SessionStats(
        files_total=len(files),
        start_time=time.perf_counter(),
    )

    print(
        f"Session logs: {log_folder}"
    )

    print()

    # --------------------------------------------------------
    # Processing
    # --------------------------------------------------------

    try:

        for number, source_file in enumerate(
            files,
            start=1,
        ):

            relative_path = (
                source_file
                .relative_to(
                    source_root
                )
            )

            destination_file = (
                destination_root
                / relative_path
            )

            print()
            print(
                f"[{number}/{len(files)}] "
                f"{relative_path}"
            )

            # ------------------------------------------------
            # Existing destination
            # ------------------------------------------------

            if (
                destination_file.exists()
                and not overwrite
            ):

                print(
                    "  [SKIP] "
                    "Destination already exists."
                )

                stats.files_skipped += 1

                file_writer.writerow(
                    [
                        str(destination_file),
                        0,
                        0,
                        0,
                        0,
                        0,
                        "skipped",
                    ]
                )

                continue

            # ------------------------------------------------
            # Write
            # ------------------------------------------------

            success = write_file(
                source=source_file,
                destination=destination_file,
                stats=stats,
                event_writer=event_writer,
                revision_writer=revision_writer,
                revision_state_writer=revision_state_writer,
                file_writer=file_writer,
            )

            if success:

                stats.files_completed += 1

            else:

                stats.files_skipped += 1

    except KeyboardInterrupt:

        print()
        print(
            "Experiment interrupted."
        )

    finally:

        event_handle.close()
        file_handle.close()
        revision_handle.close()
        revision_state_handle.close()

    # --------------------------------------------------------
    # Final statistics
    # --------------------------------------------------------

    total_runtime = (
        time.perf_counter()
        - stats.start_time
    )

    print()
    print("=" * 76)
    print(
        f"  {APP_NAME} {VERSION}"
    )
    print(
        "  SESSION COMPLETE"
    )
    print("=" * 76)

    print()

    print(
        f"  Files completed       : "
        f"{stats.files_completed}"
    )

    print(
        f"  Files skipped         : "
        f"{stats.files_skipped}"
    )

    print(
        f"  Total words           : "
        f"{stats.total_words}"
    )

    print(
        f"  Total characters      : "
        f"{stats.total_characters}"
    )

    print(
        f"  Total revisions       : "
        f"{stats.revisions_total}"
    )

    print(
        f"  Revision time         : "
        f"{format_duration(stats.total_revision_time)}"
    )

    print(
        f"  Runtime               : "
        f"{format_duration(total_runtime)}"
    )

    print()

    print(
        f"  Average model WPS     : "
        f"{stats.average_model_wps:.3f}"
    )

    print(
        f"  Overall observed WPS  : "
        f"{stats.average_wps:.3f}"
    )

    print()

    print(
        f"  Session data          : "
        f"{log_folder}"
    )

    print()

    print(
        "Revision behavior was recorded separately "
        "from the actual project files."
    )

    print()


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\n\nStopped by user."
        )

        sys.exit(0)