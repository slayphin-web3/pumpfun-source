#!/usr/bin/env bash
# Native rebuild of the byte-identical Metaplex Token Metadata program (no Docker).
#
# Mirrors what Solana 1.16.25 `cargo build-sbf` does inside the pinned
# solanafoundation/solana-verifiable-build@sha256:43206149... image used by
# scripts/pump_build_token_dependency.py: platform-tools v1.37 cargo/rustc,
# RUSTFLAGS=" -Zremap-cwd-prefix=", `cargo build --release --target sbf-solana-solana --locked`,
# then `llvm-objcopy --strip-all`.
#
# usage: build_native.sh <fresh-empty-work-dir>
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
W=$(realpath -m "$1"); [ ! -e "$W" ] || { echo "work dir must not exist: $W" >&2; exit 2; }
mkdir -p "$W/dl" "$W/pt" "$W/out"
PT_URL=https://github.com/solana-labs/platform-tools/releases/download/v1.37/platform-tools-linux-x86_64.tar.bz2
PT_SHA=8d5153589dbe19635affe937663cf4555a7e69a62d91ab4a1df064aaa8d5f066
curl -sSL -o "$W/dl/pt.tar.bz2" "$PT_URL"
echo "$PT_SHA  $W/dl/pt.tar.bz2" | sha256sum -c -
tar xjf "$W/dl/pt.tar.bz2" -C "$W/pt"
echo "7194df9c12e893cfa88fff5dd821d02d45910b4d375e13677b4723f45769a384  $W/pt/rust/bin/rustc" | sha256sum -c -
git clone -q https://github.com/metaplex-foundation/mpl-token-metadata "$W/src"
git -C "$W/src" checkout -q 17e99434af5ead3e989c08f32af33609821d0bc0
git -C "$W/src" apply --check "$HERE/source.patch"
git -C "$W/src" apply "$HERE/source.patch"
export CARGO_HOME="$W/cargo-home"
export CC="$W/pt/llvm/bin/clang" AR="$W/pt/llvm/bin/llvm-ar" OBJDUMP="$W/pt/llvm/bin/llvm-objdump" OBJCOPY="$W/pt/llvm/bin/llvm-objcopy"
export RUSTC="$W/pt/rust/bin/rustc" RUSTFLAGS=" -Zremap-cwd-prefix="
unset CARGO_TARGET_DIR
WS="$W/src/programs/token-metadata"
cd "$WS"
"$W/pt/rust/bin/cargo" build --release --target sbf-solana-solana \
  --config 'registries.crates-io.protocol="sparse"' --locked --manifest-path "$WS/Cargo.toml"
"$W/pt/llvm/bin/llvm-objcopy" --strip-all "$WS/target/sbf-solana-solana/release/token_metadata.so" "$W/out/token_metadata.so"
sha256sum "$W/out/token_metadata.so"
echo "expected 99ee61a5159e15a359b01298b52c9f9f912eb19e47bdfe83987c16de52a4b1ff (707448 bytes)"
