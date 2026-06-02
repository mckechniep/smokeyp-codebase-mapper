"""Tests for semantic_index.sh — the optional grepai bridge.

These tests use a MOCK grepai (and a mock ollama) so they run fast and
without Ollama/network. The mock reproduces the real grepai v0.35.0 watcher
lifecycle observed during the v0.6.0 brevity failure investigation:

    Indexing -> Embedding -> "Initial scan complete: N files indexed,
    M chunks created, ..." -> "Building symbol index..." ->
    "[RUNNING] <dir> - steady" -> "Watching for changes..."

The on-disk index (.grepai/index.gob) is only guaranteed valid once the
watcher reaches steady state. Killing the watcher before that point leaves a
missing or truncated index — grepai then fails with "unexpected EOF". The
build contract under test:

  * never SIGTERM the watcher before the steady-state marker appears
  * on timeout: report failure (never "indexed:N") and remove a damaged
    index the script itself created
  * never delete a .grepai directory the user created themselves
  * cleanup must not run `grepai watch --stop` (that stops the user's own
    BACKGROUND daemon, not our foreground child)
"""

import os
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "semantic_index.sh"

# Mock grepai: records every invocation to $MOCK_CALLS and simulates the
# watcher lifecycle. Behaviour knobs (env vars):
#   MOCK_SCAN_SECS      seconds the initial scan takes (default 1)
#   MOCK_CHUNKS         chunks reported at completion (default 42)
#   MOCK_NEVER_COMPLETE if set, the initial scan never finishes
#   MOCK_STATUS_CHUNKS  if set, `status` reports this chunk count even while
#                       still indexing (a mid-scan checkpoint flush — the
#                       condition that fooled the old stability heuristic)
MOCK_GREPAI = r"""#!/usr/bin/env bash
echo "$*" >> "${MOCK_CALLS:?}"
case "$1" in
  init)
    mkdir -p .grepai && touch .grepai/config.yaml
    ;;
  watch)
    # `watch --stop` is daemon IPC on real grepai: it signals a background
    # watcher and returns immediately. Never simulate a foreground watcher.
    for arg in "$@"; do
      [ "$arg" = "--stop" ] && exit 0
    done
    # Simulate the watcher crashing on startup (Ollama down, bad config).
    if [ -n "${MOCK_WATCH_DIES:-}" ]; then
      echo "Error: failed to connect to Ollama" >&2
      exit 1
    fi
    phase=indexing
    trap 'echo "killed-during:$phase" >> "$MOCK_CALLS"; exit 0' TERM INT
    if [ -z "${MOCK_NEVER_COMPLETE:-}" ]; then
      end=$(( SECONDS + ${MOCK_SCAN_SECS:-1} ))
      while [ "$SECONDS" -lt "$end" ]; do sleep 0.2; done
      echo "Initial scan complete: 5 files indexed, ${MOCK_CHUNKS:-42} chunks created, 0 files removed, 0 skipped (took 1.0s)"
      echo "Building symbol index..."
      sleep 0.3
      printf 'fake-gob-data' > .grepai/index.gob
      echo "Symbol index built: 10 symbols extracted"
      echo "[RUNNING] $PWD - steady"
      echo "Watching for changes... (Press Ctrl+C to stop)"
      phase=steady
    fi
    while true; do sleep 0.5; done
    ;;
  status)
    if [ -n "${MOCK_STATUS_CHUNKS:-}" ]; then
      echo "Total chunks: ${MOCK_STATUS_CHUNKS}"
    elif [ -f .grepai/index.gob ]; then
      echo "Total chunks: ${MOCK_CHUNKS:-42}"
    else
      echo "Total chunks: 0"
    fi
    ;;
  search)
    if [ -f .grepai/index.gob ]; then
      echo '[{"file_path":"src/x.py","start_line":1,"end_line":2,"content":"x","score":0.9}]'
    else
      echo "Error: failed to load index: failed to decode index: unexpected EOF" >&2
      exit 1
    fi
    ;;
esac
"""

MOCK_OLLAMA = r"""#!/usr/bin/env bash
if [ "$1" = "list" ]; then
  echo "nomic-embed-text:latest  0a12b3c4  274 MB  2 days ago"
fi
exit 0
"""


class SemanticIndexTestCase(unittest.TestCase):
    """Shared fixture: temp dir with mock binaries, a calls log, and a repo."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        bin_dir = self.tmp / "mockbin"
        bin_dir.mkdir()
        self.grepai = bin_dir / "grepai"
        self.grepai.write_text(MOCK_GREPAI, encoding="utf-8")
        self.grepai.chmod(0o755)
        ollama = bin_dir / "ollama"
        ollama.write_text(MOCK_OLLAMA, encoding="utf-8")
        ollama.chmod(0o755)

        self.calls = self.tmp / "calls.log"
        self.calls.touch()

        self.repo = self.tmp / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "src" / "app.py").write_text("print('hi')\n")

        self.base_env = os.environ.copy()
        self.base_env["PATH"] = f"{bin_dir}:{self.base_env['PATH']}"
        self.base_env["GREPAI_BIN"] = str(self.grepai)
        self.base_env["MOCK_CALLS"] = str(self.calls)

    def run_script(self, *args, timeout=60, **mock_env):
        env = dict(self.base_env)
        env.update({k: str(v) for k, v in mock_env.items()})
        return subprocess.run(
            ["bash", str(SCRIPT), *[str(a) for a in args]],
            capture_output=True, text=True, env=env, timeout=timeout,
        )

    def recorded_calls(self) -> str:
        return self.calls.read_text(encoding="utf-8")


class BuildTimeoutHonestyTest(SemanticIndexTestCase):
    """The brevity failure: a build that cannot finish in time must FAIL,
    not report a damaged index as a success."""

    def test_timeout_reports_failure_not_success(self):
        # Scan never completes; status shows a nonzero mid-scan checkpoint
        # count — exactly the brevity condition that produced "indexed:N"
        # followed by "unexpected EOF" on search.
        proc = self.run_script(
            "build", self.repo, 2,
            MOCK_NEVER_COMPLETE=1, MOCK_STATUS_CHUNKS=7160,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("indexed:", proc.stdout)

    def test_timeout_removes_index_dir_it_created(self):
        # No pre-existing .grepai: the script created it, so on timeout it
        # must remove it — a later `search` must not find a damaged index.
        proc = self.run_script(
            "build", self.repo, 2,
            MOCK_NEVER_COMPLETE=1, MOCK_STATUS_CHUNKS=7160,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse((self.repo / ".grepai").exists())

    def test_timeout_preserves_preexisting_user_index(self):
        # .grepai existed before the build (the user's own index): the
        # script must never delete it, even on timeout.
        user_index = self.repo / ".grepai"
        user_index.mkdir()
        (user_index / "index.gob").write_text("user's own data")
        proc = self.run_script(
            "build", self.repo, 2,
            MOCK_NEVER_COMPLETE=1, MOCK_STATUS_CHUNKS=7160,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue((user_index / "index.gob").exists())


class BuildWatcherCrashTest(SemanticIndexTestCase):
    """The watcher can die on its own (Ollama OOM-killed, model missing,
    bad config). The build must fail promptly and leave nothing behind."""

    def test_watcher_crash_fails_and_removes_created_index(self):
        proc = self.run_script("build", self.repo, 60, MOCK_WATCH_DIES=1)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("indexed:", proc.stdout)
        self.assertFalse((self.repo / ".grepai").exists())


class BuildExternalKillTest(SemanticIndexTestCase):
    """If the build itself is killed (calling session timeout, Ctrl-C), it
    must exit non-zero, reap its watcher, and leave no damaged index."""

    def test_sigterm_to_process_group_fails_cleanly(self):
        env = dict(self.base_env)
        env.update({"MOCK_NEVER_COMPLETE": "1", "MOCK_STATUS_CHUNKS": "500"})
        proc = subprocess.Popen(
            ["bash", str(SCRIPT), "build", str(self.repo), "120"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=env, start_new_session=True,
        )
        time.sleep(3)  # let init run and the watcher start
        os.killpg(proc.pid, signal.SIGTERM)  # what a session timeout does
        proc.communicate(timeout=15)  # also closes the pipes
        self.assertNotEqual(proc.returncode, 0)
        # The cleanup is asynchronous (orphaned subshell may finish last);
        # give it a moment, then assert nothing damaged was left behind.
        for _ in range(20):
            if not (self.repo / ".grepai").exists():
                break
            time.sleep(0.5)
        self.assertFalse((self.repo / ".grepai").exists())


class BuildKillTimingTest(SemanticIndexTestCase):
    """Never SIGTERM the watcher while it is still indexing/writing — that
    is what truncates index.gob and causes "unexpected EOF"."""

    def test_watcher_only_killed_after_steady_state(self):
        # Scan takes 12s; status shows nonzero "checkpoint" chunks from the
        # start. The old chunk-stability heuristic kills at ~9s (3 stable
        # polls x 3s) — mid-write. The build must instead wait for the
        # steady-state marker in the watcher output.
        proc = self.run_script(
            "build", self.repo, 30,
            MOCK_SCAN_SECS=12, MOCK_STATUS_CHUNKS=500,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        calls = self.recorded_calls()
        self.assertIn("killed-during:steady", calls)
        self.assertNotIn("killed-during:indexing", calls)


class BuildSuccessTest(SemanticIndexTestCase):
    def test_build_reports_chunk_count_and_keeps_index(self):
        proc = self.run_script("build", self.repo, 30,
                               MOCK_SCAN_SECS=1, MOCK_CHUNKS=4242)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("indexed:4242", proc.stdout)
        # The index must stay in place: `search` runs after `build`.
        self.assertTrue((self.repo / ".grepai" / "index.gob").exists())

    def test_search_works_after_successful_build(self):
        build = self.run_script("build", self.repo, 30, MOCK_SCAN_SECS=1)
        self.assertEqual(build.returncode, 0, msg=build.stderr)
        search = self.run_script("search", self.repo, "bootstrap code", 3)
        self.assertEqual(search.returncode, 0, msg=search.stderr)
        self.assertIn("file_path", search.stdout)


class HasIndexTest(SemanticIndexTestCase):
    """has-index: detect a pre-existing (warm) grepai index without building.

    The default skill flow only USES a warm index (e.g. maintained by the
    user's own `grepai watch` daemon); it never builds one. Building is
    explicit opt-in via --semantic.
    """

    def test_no_index_returns_failure(self):
        proc = self.run_script("has-index", self.repo)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("index-present", proc.stdout)

    def test_warm_index_returns_success(self):
        index_dir = self.repo / ".grepai"
        index_dir.mkdir()
        (index_dir / "index.gob").write_text("warm index data")
        proc = self.run_script("has-index", self.repo)
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("index-present", proc.stdout)

    def test_empty_grepai_dir_is_not_an_index(self):
        # .grepai exists but holds no index.gob (failed init leftovers,
        # config-only dir): not usable, must not count as warm.
        (self.repo / ".grepai").mkdir()
        proc = self.run_script("has-index", self.repo)
        self.assertNotEqual(proc.returncode, 0)

    def test_missing_repo_arg_returns_failure(self):
        proc = self.run_script("has-index")
        self.assertNotEqual(proc.returncode, 0)


class CleanupTest(SemanticIndexTestCase):
    def test_cleanup_never_calls_watch_stop(self):
        # `grepai watch --stop` stops the user's BACKGROUND daemon (their own
        # personal watcher) — not our foreground child. Cleanup must never
        # invoke it.
        build = self.run_script("build", self.repo, 30, MOCK_SCAN_SECS=1)
        self.assertEqual(build.returncode, 0, msg=build.stderr)
        self.run_script("cleanup", self.repo)
        for line in self.recorded_calls().splitlines():
            self.assertNotIn("--stop", line)

    def test_cleanup_removes_index_created_by_build(self):
        build = self.run_script("build", self.repo, 30, MOCK_SCAN_SECS=1)
        self.assertEqual(build.returncode, 0, msg=build.stderr)
        self.assertTrue((self.repo / ".grepai").exists())
        cleanup = self.run_script("cleanup", self.repo)
        self.assertEqual(cleanup.returncode, 0, msg=cleanup.stderr)
        self.assertFalse((self.repo / ".grepai").exists())

    def test_cleanup_preserves_user_owned_index(self):
        # A .grepai the user made themselves (no build ran): leave it alone.
        user_index = self.repo / ".grepai"
        user_index.mkdir()
        (user_index / "index.gob").write_text("user's own data")
        cleanup = self.run_script("cleanup", self.repo)
        self.assertEqual(cleanup.returncode, 0, msg=cleanup.stderr)
        self.assertTrue((user_index / "index.gob").exists())


if __name__ == "__main__":
    unittest.main()
