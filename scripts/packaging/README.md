# Packaging scripts

Run every script in this directory from the repository root. Each script creates
files under `dist/` that can be uploaded, copied, installed, or used as the input
to a later installer/signing step.

PyInstaller is not a cross-compiler. Native executable folders must be produced
on the same operating system family they target: macOS artifacts on macOS,
Windows artifacts on Windows, and Linux artifacts on Linux.

## Scripts and outputs

| Target | Script | Build surface | Result |
| --- | --- | --- | --- |
| Linux source distribution | `scripts/packaging/build-linux-source.sh` | Linux, macOS, or Windows with Python | Wheel and source distribution in `dist/` |
| Ubuntu package inputs | `scripts/packaging/build-ubuntu-deb.sh` | Ubuntu or Debian | Wheel and source distribution in `dist/`; Debian recipe is still WIP |
| macOS app bundle | `scripts/packaging/build-macos.sh` | macOS | `dist/LM Studio Vampire.app` |
| Windows executable folder | `scripts/packaging/build-windows.ps1` | Windows PowerShell | `dist/LMStudioVampire/` |
| HTML helper apps | `scripts/packaging/build-html-apps.sh` | Any shell with Bash | Single-file HTML apps staged in `dist/html/` |

## Method 1: download the repository to a build surface

A build surface is the machine, VM, cloud desktop, or CI runner that matches the
artifact you want to create. Use this method when you want to build locally or on
a manually controlled machine.

1. Prepare the target surface:
   - Linux or Ubuntu: install Python 3.10+ and shell tools.
   - macOS: install Python 3.10+ and the command-line developer tools if needed
     by PyInstaller.
   - Windows: install Python 3.10+ and run commands from PowerShell.
2. Download or clone the repository onto that surface.
3. Open a terminal at the repository root.
4. Run the script for the desired artifact:

   ```bash
   scripts/packaging/build-linux-source.sh
   scripts/packaging/build-ubuntu-deb.sh
   scripts/packaging/build-macos.sh
   scripts/packaging/build-html-apps.sh
   ```

   On Windows:

   ```powershell
   .\scripts\packaging\build-windows.ps1
   ```

5. Collect the generated files from `dist/`.
6. Run the packaging smoke test in `packaging/common/smoke-test.md` on a clean
   machine or VM before publishing the artifact.

Use this path for manual release candidates, reproducing CI output, or building
on owned hardware that has access to platform signing tools.

## Method 2: use GitHub Actions as the build surface

GitHub Actions can provide fresh Linux, macOS, and Windows build surfaces. This
is the preferred path for repeatable packaging because every run starts from the
same repository revision and can upload the generated `dist/` files as workflow
artifacts.

Create a packaging workflow that:

1. Runs on `workflow_dispatch`, tags, releases, or the branch policy used for
   packaging.
2. Checks out the repository with `actions/checkout`.
3. Sets up Python with `actions/setup-python`.
4. Runs the existing CI validation before packaging when appropriate.
5. Uses a runner that matches the artifact:
   - `ubuntu-latest` for Linux source, Ubuntu package inputs, and HTML staging.
   - `macos-latest` for `dist/LM Studio Vampire.app`.
   - `windows-latest` for `dist/LMStudioVampire/`.
6. Runs the matching script from the repository root.
7. Uploads the resulting `dist/` files with `actions/upload-artifact`.
8. Optionally attaches those artifacts to a GitHub Release.

Signing and notarization should also happen in Actions when release credentials
are available. Store signing certificates, passwords, API keys, and notarization
credentials in GitHub Actions secrets; never commit them to the repository.

This repository implements this method in `.github/workflows/packaging.yml`. The
workflow runs on `workflow_dispatch`, `v*` tags, and published releases; it
validates the code with the CI checks, builds the Linux source distribution and
HTML staging on `ubuntu-latest`, the macOS app bundle on `macos-latest`, and the
Windows executable folder on `windows-latest`, uploads each `dist/` as a
workflow artifact, and attaches zipped bundles with checksums to published
releases.

## Method 3: other ways to produce executable folders

The scripts are the canonical entry points, but the final result can also be a
folder of executables produced by other controlled build surfaces:

- **Manual PyInstaller invocation:** install the package and run the platform
  spec directly, for example `pyinstaller packaging/windows/LMStudioVampire.spec`
  or `pyinstaller packaging/macos/LMStudioVampire.spec`. This is useful when
  iterating on a spec file, but release builds should return to the scripts.
- **Containerized Linux build:** run the Linux source or HTML scripts inside a
  pinned Linux container image. This works for source distributions and staged
  HTML files, but it does not replace native Windows or macOS runners.
- **Ephemeral VM or cloud desktop:** provision a clean Windows, macOS, or Linux
  VM, download the repository, run the relevant script, export `dist/`, and
  destroy the VM. This gives a repeatable clean-room build without keeping a
  permanent release machine.
- **Installer wrapping step:** use an already produced executable folder as the
  input to an installer. For example, after `dist/LMStudioVampire/` exists on
  Windows, compile `packaging/windows/installer.iss` with Inno Setup to create a
  setup executable.
- **Release assembly job:** collect `dist/` folders produced by multiple native
  surfaces, then place them into a release bundle or upload them as separate
  artifacts. The assembly job should not rebuild native executables; it should
  only rename, checksum, sign, or upload files already created on the right
  surface.

Regardless of the production method, keep the artifact provenance clear: record
the commit SHA, the surface that built it, the script or command used, and any
signing or installer step applied after the executable folder was created.
