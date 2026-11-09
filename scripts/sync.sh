#!/usr/bin/env bash
set -euo pipefail

variant="${1:-github}"
repo="$(cd "$(dirname "$0")/.." && pwd)"

git -C "$repo" pull --ff-only

case "$variant" in
  github) source="$repo/skills" ;;
  ado) source="$repo/skills-ado" ;;
  *) echo "usage: $0 [github|ado]" >&2; exit 1 ;;
esac

for target in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
  mkdir -p "$target"
  for skill in "$source"/*/; do
    name="$(basename "$skill")"
    rm -rf "${target:?}/$name"
    cp -R "$skill" "$target/$name"
  done
  echo "Installed $variant skills to $target"
done
