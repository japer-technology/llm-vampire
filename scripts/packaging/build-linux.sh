#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

tag_args=()
if [[ -n "${RELEASE_TAG:-}" ]]; then
  tag_args=(--tag "${RELEASE_TAG}")
fi
version="$(python scripts/packaging/version.py "${tag_args[@]}")"
architecture="$(uname -m)"
case "${architecture}" in
  x86_64|amd64) architecture="x86_64" ;;
  arm64|aarch64) architecture="arm64" ;;
  *) echo "error: unsupported Linux architecture: ${architecture}" >&2; exit 1 ;;
esac

export RELEASE_VERSION="${version}"
build_dir="${repo_root}/build/pyinstaller-linux"
output="${repo_root}/dist/LMStudio-Vampire-${version}-linux-${architecture}.tar.gz"
rm -rf "${build_dir}"
mkdir -p "${build_dir}" "${repo_root}/dist"

uv run --frozen --extra packaging pyinstaller \
  --clean --noconfirm \
  --distpath "${build_dir}/dist" \
  --workpath "${build_dir}/work" \
  packaging/linux/LMStudioVampire.spec

test -x "${build_dir}/dist/LMStudioVampire/LMStudioVampire"
tar --sort=name --mtime="@${SOURCE_DATE_EPOCH:-0}" --owner=0 --group=0 --numeric-owner \
  -C "${build_dir}/dist" -czf "${output}" LMStudioVampire
test -s "${output}"
printf 'Built %s\n' "${output}"
