#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source ../toolchain.env
source BASE.env
[[ $(uname -m) == aarch64 ]] || { echo "Steam bootstrap requires aarch64" >&2; exit 1; }
rm -rf out
mkdir -p out work
podman build --build-arg "BUILDER_IMAGE=${BUILDER_IMAGE}" \
    -t localhost/armada-steam-bootstrap-builder -f Containerfile .
podman run --rm --volume "${PWD}:/work:Z" --workdir /work \
    localhost/armada-steam-bootstrap-builder \
    bash -euo pipefail -c 'python3 test.py; source BASE.env; python3 fetch.py "$STEAM_CLIENT_VERSION" "$STEAM_RUNTIME_VERSION" "$STEAM_RUNTIME_SHA256"'
podman run --rm --network none --volume "${PWD}:/work:Z" --workdir /work \
    localhost/armada-steam-bootstrap-builder bash generate.sh
