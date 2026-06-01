#!/usr/bin/env bash
#
# semantic_index.sh — optional semantic-search bridge for the codebase mapper.
#
# Wraps `grepai` (vector code search backed by a local Ollama embedding model)
# so the LLM evaluation step (SKILL.md Step 1.5) can RETRIEVE the most relevant
# code for a question instead of guessing from a bounded evidence pack. This is
# strictly an enrichment-layer aid: the deterministic scan and the renderer
# never touch it, so the report stays reproducible.
#
# Every subcommand degrades gracefully. If grepai or Ollama (or the embedding
# model) is missing, `available` exits non-zero and callers fall back to the
# deterministic-only / evidence-pack flow — semantic mode is purely additive.
#
# Usage:
#   semantic_index.sh available
#   semantic_index.sh build   <repo> [timeout_secs]   # default 300
#   semantic_index.sh search  <repo> <query> [n]       # default 5; prints grepai JSON
#   semantic_index.sh cleanup <repo>
#
# Notes:
#   * Indexing uses an isolated FOREGROUND watcher (our own child process), so it
#     never stops or interferes with a `grepai watch --background` daemon the user
#     may already be running for their own work.
#   * Build succeeds only when the watcher reaches steady state (index fully
#     written). On timeout it reports failure and removes the index it created —
#     a partially written index.gob would poison later searches with
#     "unexpected EOF". Size the timeout to the repo (large repos need more).
#   * `grepai init` appends `.grepai/` to the repo's .gitignore. `cleanup` removes
#     the `.grepai/` index directory only if build created it (marker file
#     `.grepai/.codemap-created`); a user's own pre-existing index is never deleted.
#   * Indexing respects the repo's .gitignore. Vendored code not covered by
#     .gitignore will be indexed too (cost); that is acceptable for retrieval.

set -uo pipefail

GREPAI="${GREPAI_BIN:-grepai}"
EMBED_MODEL="${GREPAI_MODEL:-nomic-embed-text}"

err() { echo "[semantic_index] $*" >&2; }

# Exit 0 only when grepai + ollama + the embedding model are all present.
cmd_available() {
  command -v "$GREPAI" >/dev/null 2>&1 || { err "grepai not on PATH"; return 1; }
  command -v ollama   >/dev/null 2>&1 || { err "ollama not on PATH"; return 1; }
  if ! ollama list 2>/dev/null | grep -q "$EMBED_MODEL"; then
    err "ollama model '$EMBED_MODEL' not pulled (try: ollama pull $EMBED_MODEL)"
    return 1
  fi
  echo "available"
  return 0
}

# Build (or refresh) the index for <repo>. Prints "indexed:<chunks>" on success.
#
# Completion is detected from the WATCHER'S OWN OUTPUT, not from polled chunk
# counts. `grepai status` can report nonzero chunks while the initial scan is
# still writing (mid-scan checkpoints), and SIGTERM during a write makes
# grepai's shutdown force-abort ("shutdown timeout"), leaving a truncated
# index.gob that fails every later read with "unexpected EOF". The watcher is
# only stopped once it logs its steady-state marker — stopping it then is
# graceful and safe.
cmd_build() {
  local repo="${1:-}" tmo="${2:-300}"
  [ -n "$repo" ] && [ -d "$repo" ] || { err "build: no such repo: '$repo'"; return 1; }
  cmd_available >/dev/null || return 1

  (
    cd "$repo" || exit 1

    # Track whether WE created the index dir: only then may build (on
    # timeout) or cleanup remove it. A pre-existing .grepai is the user's
    # own index and is never deleted.
    local created_marker=".grepai/.codemap-created"
    if [ ! -d .grepai ]; then
      "$GREPAI" init --yes --provider ollama >/dev/null 2>&1 \
        || { err "grepai init failed in $repo"; exit 1; }
      # The marker is the linchpin of the cleanup contract ("only delete what
      # we created") — if it cannot be written, do not proceed.
      touch "$created_marker" \
        || { err "cannot write $created_marker"; rm -rf .grepai; exit 1; }
    fi

    local watch_log
    watch_log=$(mktemp) || exit 1

    # Isolated foreground watcher as our own child process; its stdout is the
    # lifecycle log we wait on.
    "$GREPAI" watch --no-ui >"$watch_log" 2>&1 &
    local wpid=$! build_ok=no

    # Single cleanup path for EVERY exit (success, timeout, watcher crash,
    # external signal): reap the watcher, drop the temp log, and — unless the
    # build completed — remove an index WE created. A partially written
    # index.gob poisons every later search with "unexpected EOF".
    _build_cleanup() {
      [ -n "$wpid" ] && { kill "$wpid" 2>/dev/null; wait "$wpid" 2>/dev/null; }
      [ "$build_ok" = yes ] || { [ -f "$created_marker" ] && rm -rf .grepai; }
      rm -f "$watch_log"
      return 0
    }
    trap _build_cleanup EXIT
    # Make external interruption deterministic: exit (firing the EXIT trap)
    # instead of resuming the poll loop mid-signal.
    trap 'exit 130' INT
    trap 'exit 143' TERM

    local deadline=$(( SECONDS + tmo )) ready=no
    while [ "$SECONDS" -lt "$deadline" ]; do
      sleep 1
      if grep -qE 'Watching for changes|\[RUNNING\].*steady' "$watch_log" 2>/dev/null; then
        ready=yes
        break
      fi
      # Watcher died on its own (config error, Ollama down, ...): fail now.
      kill -0 "$wpid" 2>/dev/null || break
    done

    if [ "$ready" != yes ]; then
      # Timed out (or the watcher died) before the index was fully written.
      # The EXIT trap reaps the watcher and removes the index if we created it.
      err "index watcher exited or did not complete within ${tmo}s (large repo? pass a bigger timeout); falling back to non-semantic mode"
      exit 1
    fi

    # Steady state: the index is fully written; stopping the watcher here is
    # a graceful shutdown. Reap it now and clear wpid so the EXIT trap cannot
    # wait on a recycled pid.
    kill "$wpid" 2>/dev/null
    wait "$wpid" 2>/dev/null
    wpid=""

    local chunks
    chunks=$(sed -n 's/.*Initial scan complete:.*[^0-9]\([0-9][0-9]*\) chunks created.*/\1/p' "$watch_log" | tail -1)
    chunks=${chunks:-0}

    if [ "$chunks" -gt 0 ]; then
      build_ok=yes
      echo "indexed:$chunks"
    else
      err "watcher reached steady state but indexed 0 chunks"
      exit 1
    fi
  )
}

# Semantic search within <repo>'s index. Prints grepai's JSON array.
cmd_search() {
  local repo="${1:-}" query="${2:-}" n="${3:-5}"
  [ -n "$repo" ] && [ -d "$repo/.grepai" ] || { err "search: no index at '$repo/.grepai' (run build first)"; return 1; }
  [ -n "$query" ] || { err "search: empty query"; return 1; }
  ( cd "$repo" && "$GREPAI" search "$query" -j -n "$n" 2>/dev/null )
}

# Remove the index directory — but ONLY if our build created it. A .grepai
# the user made for their own grepai usage is never touched. We also never
# call `grepai watch --stop` here: that is daemon IPC for a *background*
# watcher (i.e. the user's own daemon), not for the foreground child that
# cmd_build manages and reaps itself.
cmd_cleanup() {
  local repo="${1:-}"
  if [ -n "$repo" ] && [ -f "$repo/.grepai/.codemap-created" ]; then
    rm -rf "$repo/.grepai"
  fi
  echo "cleaned"
}

main() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    available) cmd_available "$@" ;;
    build)     cmd_build "$@" ;;
    search)    cmd_search "$@" ;;
    cleanup)   cmd_cleanup "$@" ;;
    *)
      err "usage: $0 {available | build <repo> [timeout] | search <repo> <query> [n] | cleanup <repo>}"
      return 2
      ;;
  esac
}

main "$@"
