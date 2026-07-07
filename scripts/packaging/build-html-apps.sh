#!/usr/bin/env bash
set -euo pipefail

# Collect the self-contained single-file HTML/JS/CSS helper apps into dist/html/.
# Each file in packaging/html/ is a standalone application that needs no build
# step; this script simply validates and stages them for distribution.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
src_dir="${repo_root}/packaging/html"
out_dir="${repo_root}/dist/html"

if [[ ! -d "${src_dir}" ]]; then
  echo "error: ${src_dir} not found" >&2
  exit 1
fi

shopt -s nullglob
html_files=("${src_dir}"/*.html)
shopt -u nullglob

if [[ ${#html_files[@]} -eq 0 ]]; then
  echo "error: no .html apps found in ${src_dir}" >&2
  exit 1
fi

mkdir -p "${out_dir}"

for src in "${html_files[@]}"; do
  name="$(basename "${src}")"
  cp "${src}" "${out_dir}/${name}"
  echo "staged ${name} -> dist/html/${name}"
done

echo "Built ${#html_files[@]} HTML app(s) into ${out_dir}."
