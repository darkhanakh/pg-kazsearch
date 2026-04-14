#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

cargo build --release -p kazsearch-elastic
target_dir="$(cargo metadata --no-deps --format-version 1 | python3 -c 'import json,sys; print(json.load(sys.stdin)["target_directory"])')"

os_name="$(uname -s | tr '[:upper:]' '[:lower:]')"
case "$os_name" in
  linux*) platform_os="linux"; ext="so" ;;
  darwin*) platform_os="darwin"; ext="dylib" ;;
  *)
    echo "Unsupported OS for native copy: $os_name" >&2
    exit 1
    ;;
esac

arch_name="$(uname -m)"
case "$arch_name" in
  x86_64|amd64) platform_arch="x86_64" ;;
  arm64|aarch64) platform_arch="aarch64" ;;
  *)
    echo "Unsupported architecture for native copy: $arch_name" >&2
    exit 1
    ;;
esac

source_path="${target_dir}/release/libkazsearch_elastic.${ext}"
if [[ ! -f "$source_path" ]]; then
  echo "Native library not found: $source_path" >&2
  exit 1
fi

dest_dir="elastic/java/src/main/resources/native/${platform_os}-${platform_arch}"
mkdir -p "$dest_dir"
cp "$source_path" "$dest_dir/"

echo "Copied ${source_path} -> ${dest_dir}/"
