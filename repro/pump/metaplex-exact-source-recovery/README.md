# Metaplex Token Metadata — byte-identical reconstruction

**The captured Token Metadata payload is reproduced exactly: 0 differing positions (accepted candidate11: 1,509).**

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Captured payload `evidence/dependencies/token_metadata/deployed.so` | 793,991 | `31f0a627dba051a938de650464e55cc5397a4be0fd496929c1f9cf02fe5e9011` |
| Raw compiler output `token_metadata.so` (this package) | 707,448 | `99ee61a5159e15a359b01298b52c9f9f912eb19e47bdfe83987c16de52a4b1ff` |
| Raw output + 86,543 regenerated zero bytes | 793,991 | `31f0a627dba051a938de650464e55cc5397a4be0fd496929c1f9cf02fe5e9011` |

The raw compiler output equals the complete captured ELF extent byte for byte. The remaining 86,543 captured bytes are verified all-zero allocation; they are regenerated as zeros, never copied. No executable, relocation, header or padding bytes were edited.

Source: public [`mpl-token-metadata@17e99434`](https://github.com/metaplex-foundation/mpl-token-metadata/tree/17e99434af5ead3e989c08f32af33609821d0bc0) plus `source.patch` (18 files under `programs/token-metadata/program/src`). `delta-from-candidate11.patch` shows exactly what changed relative to accepted [candidate11](../metaplex-candidate-build-11/README.md).

## 1. Utilize: separate zero-use rejection in front of the unchanged upstream guard

All 1,477 `.text` and 2 `.rel.dyn` differences were inside Utilize. The deployed code is the upstream guard left intact, with the audit-era zero check added as its own statement:

```rust
if number_of_uses == 0 {
    return Err(MetadataError::NotEnoughUses.into());
}
if number_of_uses > metadata_uses.total || number_of_uses > metadata_uses.remaining {
    return Err(MetadataError::NotEnoughUses.into());
}
let remaining_uses = metadata_uses
    .remaining
    .checked_sub(number_of_uses)
    .ok_or(MetadataError::NotEnoughUses)?;
```

Candidates 11–14 merged the zero check into one guard or rewrote the subtraction. `utilize-variants.json` keeps every spelling built in this pass, each over candidate11's layout:

| Variant | Guard shape | Differing positions | Utilize window |
| --- | --- | ---: | ---: |
| v12 | `n == 0 \|\| n > total`, then `checked_sub` (= hosted candidate12/13) | 196,601 | 1,585 |
| v4 / v6 / v7 | split zero/total checks; `match checked_sub`; explicit `remaining < n` | 196,601 (same bytes as v12) | 1,585 |
| v3 | upstream guard, then zero check | 157 | 127 |
| **v2** | **zero check, then upstream guard and `checked_sub`** | **30** | **0** |

After v2, the only residual was 30 bytes of panic line numbers.

## 2. The 29 panic `Location` records (30 bytes)

`location-records.json` lists every corrected record. All 287 decoded records now equal the original. Lines move only through source constructs; code generation is unchanged (the full `.text` was already equal after v2).

| File | Sites | What sets the original line/column |
| --- | ---: | --- |
| `processor/uses/utilize.rs` | 1 | `TokenStandard` joins the existing `crate::state::{…}` import (rustfmt reflows it to 4 lines); the token-standard check uses the `Some(X) \| Some(Y)` style already used upstream in `mint.rs`/`print.rs` (9 lines) |
| `processor/uses/approve_use_authority.rs` | 2 | same import + check style; `system_program` joins the `solana_program::{…}` import (+1 line) |
| `processor/uses/revoke_use_authority.rs` | 2 | same import + check style (import still fits one line) |
| `processor/mod.rs` | 3 | `Some(ProgrammableNonFungible) \| Some(ProgrammableNonFungibleEdition)` — the existing upstream style |
| `processor/edition/create_master_edition_v3.rs` | 1 | `system_program` imported (rustfmt reflows the import to 3 lines) |
| `processor/edition/convert_master_edition_v1_to_v2.rs` | 3 | column 30 forces a 24-character receiver: `master_edition_info_data`, the file-wide `<account>_data` idiom; offsets use the existing `MASTER_EDITION_FEE_FLAG_OFFSET`/`MASTER_EDITION_TOKEN_STANDARD_OFFSET` constants (import reflows +3) |
| `utils/metadata.rs` | 8 | `system_program` import (+2) and the three upstream `IMPORTANT NOTE` comment lines retained above the now-plain assertion (+3) |
| `processor/burn/nonfungible.rs` | 5 | the new `crate::assertions` import sits in its own group above `use super::*;` (+1 blank line) |
| `processor/metadata/transfer.rs` | 4 | one comment line above the self-transfer early return |

**Disclosure — this is the repository's "source coordinate" category.** The first six rows are deterministic once the construct is chosen: rustfmt (the upstream CI runs `cargo fmt --check`) places every line. The last three rows have line *counts and positions* fixed by bracketing Location sites, but their *text* is not recoverable from the binary: a blank import-group line, one comment (`// Transferring to the same token account is a no-op.`), and three retained upstream comment lines. Any text with the same line counts produces identical bytes. These five lines are the only non-code choices in the package; reviewers who reject them can drop them and the residual returns to exactly those Location records.

## 3. Recipe

`build_native.sh` reproduces the hosted image recipe without Docker: official platform-tools v1.37 (archive `8d5153589dbe19635affe937663cf4555a7e69a62d91ab4a1df064aaa8d5f066`, rustc `7194df9c…`, the same compiler recorded in candidate11's `tool-versions.json`), `RUSTFLAGS=" -Zremap-cwd-prefix="`, `cargo build --release --target sbf-solana-solana --locked`, then `llvm-objcopy --strip-all`, exactly as Solana 1.16.25 `cargo build-sbf` does. Equivalence with the hosted path is measured, not assumed: the same native recipe reproduces hosted candidate11 (`3bbaf27f…`) and candidate12/13 (`4f039033…`) byte for byte. A clean-room rebuild (fresh upstream checkout, `git apply source.patch`, fresh `CARGO_HOME` and target) produced the same `99ee61a5…`; its log is `build.log.gz`.

`source.patch` and `source-inputs.json` use the existing recovery-package format read by `scripts/pump_build_token_dependency.py`. The script and workflows are not modified here because the pass-27 current guard pins their hashes; wiring a `--metaplex-exact-recovery` flag to this directory is a maintainer integration step.

## Verify

```sh
python3 -B repro/pump/metaplex-exact-source-recovery/verify.py          # offline, stdlib only
repro/pump/metaplex-exact-source-recovery/build_native.sh /tmp/mpl-exact  # full rebuild, ~3 min, network
```

The verifier checks the manifest, the patch/input bindings, the retained raw output, raw-to-ELF-extent equality, the all-zero allocation tail, padded whole-payload equality and all 287 Location records.

## Scope

- Dependency capture images move from **2/5 to 3/5** (SPL Token, Token-2022, Metaplex). Under the repository's stricter definition, whole-file raw compiler output exactness stays **1/5**: Metaplex's capture is an allocation image, although its raw output now equals the entire ELF extent.
- Identical bytes imply identical on-chain behavior; the inherited 135 Metaplex comparisons were not rerun.
- This is a source tree that compiles to the deployed bytes under the pinned recipe. It is not proof that the authors' literal text matches, notably for the comment/blank lines disclosed above.
- Core program identity is unchanged at 0/4. ATA remains at 307 differing bytes.
