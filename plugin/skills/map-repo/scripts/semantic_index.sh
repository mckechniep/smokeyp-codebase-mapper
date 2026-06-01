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
#   * `grepai init` appends `.grepai/` to the repo's .gitignore; `cleanup` removes
#     the `.grepai/` index directory afterwards.
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
cmd_build() {
  local repo="${1:-}" tmo="${2:-300}"
  [ -n "$repo" ] && [ -d "$repo" ] || { err "build: no such repo: '$repo'"; return 1; }
  cmd_available >/dev/null || return 1

  (
    cd "$repo" || exit 1
    if [ ! -d .grepai ]; then
      "$GREPAI" init --yes --provider ollama >/dev/null 2>&1 \
        || { err "grepai init failed in $repo"; exit 1; }
    fi

    # Isolated foreground watcher as our own child; poll the index until the
    # chunk count is nonzero and stable, then stop it. Early-exits as soon as
    # the initial index settles instead of waiting the full timeout.
    "$GREPAI" watch --no-ui >/dev/null 2>&1 &
    local wpid=$! prev=-1 stable=0 chunks=0 deadline=$(( SECONDS + tmo ))
    while [ "$SECONDS" -lt "$deadline" ]; do
      sleep 3
      chunks=$("$GREPAI" status --no-ui 2>/dev/null \
                 | sed -n 's/.*Total chunks:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)
      chunks=${chunks:-0}
      if [ "$chunks" -gt 0 ] && [ "$chunks" = "$prev" ]; then
        stable=$((stable + 1))
        [ "$stable" -ge 2 ] && break
      else
        stable=0
      fi
      prev=$chunks
    done
    kill "$wpid" 2>/dev/null
    wait "$wpid" 2>/dev/null

    if [ "${chunks:-0}" -gt 0 ]; then
      echo "indexed:$chunks"
    else
      err "no chunks indexed within ${tmo}s"
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

# Stop any watcher we may have left and remove the index directory.
cmd_cleanup() {
  local repo="${1:-}"
  command -v "$GREPAI" >/dev/null 2>&1 && "$GREPAI" watch --stop >/dev/null 2>&1
  if [ -n "$repo" ] && [ -d "$repo/.grepai" ]; then
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
