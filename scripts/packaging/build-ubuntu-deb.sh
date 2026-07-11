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

application_dir="${repo_root}/build/pyinstaller-linux/dist/LMStudioVampire"
executable="${application_dir}/LMStudioVampire"
if [[ "${reuse_linux_build}" == false ]]; then
  scripts/packaging/build-linux.sh
elif [[ ! -x "${executable}" ]]; then
  echo "error: --reuse-linux-build requires a completed build-linux.sh output" >&2
  exit 1
fi

package_root="${repo_root}/build/deb/lmstudio-vampire"
output="${repo_root}/dist/LMStudio-Vampire-${version}-linux-${artifact_architecture}.deb"
rm -rf "${package_root}"
mkdir -p "${package_root}/opt/lmstudio-vampire" "${package_root}/usr/bin"
cp -a "${application_dir}/." "${package_root}/opt/lmstudio-vampire/"
ln -s /opt/lmstudio-vampire/LMStudioVampire "${package_root}/usr/bin/vampire-desktop"
install -Dm644 packaging/ubuntu/lmstudio-vampire.desktop \
  "${package_root}/usr/share/applications/lmstudio-vampire.desktop"
install -Dm644 LICENSE.md \
  "${package_root}/usr/share/doc/lmstudio-vampire/copyright"
mkdir -p "${package_root}/DEBIAN"
cat > "${package_root}/DEBIAN/control" <<EOF
Package: lmstudio-vampire
Version: ${version}
Section: net
Priority: optional
Architecture: ${architecture}
Maintainer: japer-technology
Description: Private AI compute gateway for LM Studio
 LM Studio Vampire routes owner-approved LM Studio API endpoints and serves
 a local browser dashboard.
EOF

mkdir -p "${repo_root}/dist"
dpkg-deb --root-owner-group --build "${package_root}" "${output}"
test -s "${output}"
printf 'Built %s\n' "${output}"
