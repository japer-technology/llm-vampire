#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

reuse_linux_build=false
if [[ "${1:-}" == "--reuse-linux-build" ]]; then
  reuse_linux_build=true
elif [[ $# -ne 0 ]]; then
  echo "usage: $0 [--reuse-linux-build]" >&2
  exit 2
fi

tag_args=()
if [[ -n "${RELEASE_TAG:-}" ]]; then
  tag_args=(--tag "${RELEASE_TAG}")
fi
version="$(python scripts/packaging/version.py "${tag_args[@]}")"
machine="$(uname -m)"
case "${machine}" in
  x86_64|amd64) architecture="amd64"; artifact_architecture="x86_64" ;;
  arm64|aarch64) architecture="arm64"; artifact_architecture="arm64" ;;
  *) echo "error: unsupported Debian architecture: ${machine}" >&2; exit 1 ;;
esac

application_dir="${repo_root}/build/pyinstaller-linux/dist/LLMVampire"
executable="${application_dir}/LLMVampire"
if [[ "${reuse_linux_build}" == false ]]; then
  scripts/packaging/build-linux.sh
elif [[ ! -x "${executable}" ]]; then
  echo "error: --reuse-linux-build requires a completed build-linux.sh output" >&2
  exit 1
fi

package_root="${repo_root}/build/deb/llm-vampire"
output="${repo_root}/dist/LLM-Vampire-${version}-linux-${artifact_architecture}.deb"
rm -rf "${package_root}"
mkdir -p "${package_root}/opt/llm-vampire" "${package_root}/usr/bin"
cp -a "${application_dir}/." "${package_root}/opt/llm-vampire/"
ln -s /opt/llm-vampire/LLMVampire "${package_root}/usr/bin/vampire-desktop"
install -Dm644 packaging/ubuntu/llm-vampire.desktop \
  "${package_root}/usr/share/applications/llm-vampire.desktop"
install -Dm644 LICENSE.md \
  "${package_root}/usr/share/doc/llm-vampire/copyright"
mkdir -p "${package_root}/DEBIAN"
cat > "${package_root}/DEBIAN/control" <<EOF
Package: llm-vampire
Version: ${version}
Section: net
Priority: optional
Architecture: ${architecture}
Maintainer: japer-technology
Description: Provider-neutral local LLM aggregation gateway
 LLM Vampire discovers and routes owner-approved local LLM services behind
 one OpenAI-compatible gateway and browser dashboard.
EOF

mkdir -p "${repo_root}/dist"
dpkg-deb --root-owner-group --build "${package_root}" "${output}"
test -s "${output}"
printf 'Built %s\n' "${output}"
