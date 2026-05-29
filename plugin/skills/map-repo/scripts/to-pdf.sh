#!/usr/bin/env bash
# Convert an HTML file to PDF using a headless Chromium-family browser.
#
# Usage: to-pdf.sh <input.html> <output.pdf>
#
# Detects (in order): google-chrome, google-chrome-stable, chromium,
# chromium-browser, microsoft-edge, brave-browser. If none are available
# the script exits with status 1 and a clear message — the caller can
# then fall back to suggesting the user open the HTML manually.

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <input.html> <output.pdf>" >&2
  exit 2
fi

input="$1"
output="$2"

if [[ ! -f "$input" ]]; then
  echo "error: input not found: $input" >&2
  exit 2
fi

# Need an absolute path for the file:// URL.
case "$input" in
  /*) abs_input="$input" ;;
  *)  abs_input="$(pwd)/$input" ;;
esac

# Make sure the destination directory exists.
mkdir -p "$(dirname "$output")"

# Probe known Chromium-family binaries.
browser=""
for candidate in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge brave-browser; do
  if command -v "$candidate" >/dev/null 2>&1; then
    browser="$candidate"
    break
  fi
done

if [[ -z "$browser" ]]; then
  cat >&2 <<'EOF'
error: no Chromium-family browser found.

Install one of: google-chrome, chromium, microsoft-edge, brave-browser.

  Debian/Ubuntu:  sudo apt install chromium-browser
  macOS:          brew install --cask google-chrome
  Windows/WSL:    install Chrome on Windows, ensure it's on PATH

The HTML report is still valid; open it in any browser to view or print.
EOF
  exit 1
fi

# --no-sandbox is required when running as root (common in containers/WSL).
# --no-pdf-header-footer suppresses Chrome's default URL/timestamp header.
"$browser" \
  --headless \
  --disable-gpu \
  --no-sandbox \
  --no-pdf-header-footer \
  --print-to-pdf="$output" \
  "file://${abs_input}" >/dev/null 2>&1

if [[ ! -f "$output" ]]; then
  echo "error: $browser ran but produced no output at $output" >&2
  exit 1
fi

echo "rendered PDF -> $output"
