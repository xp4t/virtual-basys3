#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p third_party build

checkout_dependency() {
    local destination="$1" upstream_url="$2" revision="$3" sparse_path="${4:-}"
    if [ ! -e "$destination" ]; then
        git clone --filter=blob:none --no-checkout "$upstream_url" "$destination"
        if [ -n "$sparse_path" ]; then
            git -C "$destination" sparse-checkout set "$sparse_path"
        fi
        git -C "$destination" checkout --detach "$revision"
    fi
    test "$(git -C "$destination" rev-parse HEAD)" = "$revision" || {
        echo "Dependency revision mismatch at $destination; expected $revision" >&2
        exit 1
    }
}

checkout_dependency third_party/prjxray https://github.com/f4pga/prjxray.git c9f02d8576042325425824647ab5555b1bc77833
checkout_dependency third_party/prjxray-db https://github.com/f4pga/prjxray-db.git 0a0addedd73e7e4139d52a6d8db4258763e0f1f3 artix7
checkout_dependency third_party/fasm2bels https://github.com/chipsalliance/f4pga-xc-fasm2bels.git bafbcd8727e0807d6a620d1cf5dd151111c4a322
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/pip install --upgrade pip setuptools wheel
.venv/bin/pip install 'Cython==0.29.37' pkgconfig setuptools_scm
# The interchange dependency pins pycapnp 1.1.0. It requires Cython 0.29,
# so build it explicitly outside pip's otherwise incompatible isolated environment.
# Its bundled Cap'n Proto project also declares a pre-3.5 CMake policy baseline,
# which CMake 4 no longer accepts unless the compatibility floor is explicit.
CMAKE_POLICY_VERSION_MINIMUM=3.5 \
    .venv/bin/pip install --no-build-isolation 'pycapnp==1.1.0'
.venv/bin/pip install -r bitstream-decode/requirements.txt
.venv/bin/pip check
