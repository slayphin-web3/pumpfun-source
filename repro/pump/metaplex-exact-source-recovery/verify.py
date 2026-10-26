#!/usr/bin/env python3
"""Offline verifier for the byte-identical Metaplex Token Metadata reconstruction.

Standard library only. Runs no compiler, VM or network access. Checks:
  1. every package file against manifest.json;
  2. source-inputs.json <-> source.patch consistency (same 18 files, patch hash);
  3. the retained raw compiler output against comparison.json;
  4. (repository mode, default) the captured original: the raw output equals the
     complete captured ELF extent, the remaining captured allocation is all zero, and
     the zero-padded output is byte-for-byte equal to the captured payload;
  5. all 287 decoded panic Location records are equal, including the 29 records
     that differed in accepted candidate11.

To rebuild from source instead of trusting the retained output, run build_native.sh
(network + ~3 minutes) and compare its printed hash with comparison.json.
"""
import argparse
import hashlib
import json
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
sha = lambda b: hashlib.sha256(b).hexdigest()


def sections(b):
    shoff = struct.unpack_from('<Q', b, 40)[0]
    entsize, count, idx = struct.unpack_from('<HHH', b, 58)
    raw = [struct.unpack_from('<IIQQQQIIQQ', b, shoff + i * entsize) for i in range(count)]
    names = b[raw[idx][4]:raw[idx][4] + raw[idx][5]]
    return {names[r[0]:].split(b'\0', 1)[0].decode(): (r[4], r[5]) for r in raw}


def locations(b):
    secs = sections(b)
    ro, rs = secs['.rel.dyn']
    rel = {struct.unpack_from('<Q', b, o)[0]: struct.unpack_from('<Q', b, o + 8)[0] for o in range(ro, ro + rs, 16)}
    d0, ds = secs['.data.rel.ro']
    out = {}
    for off in range(d0, d0 + ds - 23, 8):
        if rel.get(off) != 8:
            continue
        ptr, ln = struct.unpack_from('<QQ', b, off)
        tgt = ptr >> 32 if ptr >> 32 else ptr
        if not 0 < ln < 400 or tgt + ln > len(b):
            continue
        s = b[tgt:tgt + ln]
        if not s.endswith(b'.rs'):
            continue
        line, col = struct.unpack_from('<II', b, off + 16)
        out[off] = (s.decode(), line, col)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', type=pathlib.Path, default=HERE.parents[2])
    ap.add_argument('--package-only', action='store_true', help='skip checks that need the captured original')
    a = ap.parse_args()

    manifest = json.loads((HERE / 'manifest.json').read_text())
    listed = set(manifest['files'])
    present = {p.name for p in HERE.iterdir() if p.is_file() and p.name not in ('manifest.json',) and not p.name.endswith('.pyc')}
    assert listed == present, ('package file set differs from manifest', sorted(listed ^ present))
    for name, rec in manifest['files'].items():
        data = (HERE / name).read_bytes()
        assert len(data) == rec['bytes'] and sha(data) == rec['sha256'], name

    inputs = json.loads((HERE / 'source-inputs.json').read_text())
    patch = (HERE / 'source.patch').read_text()
    patched_in_patch = {l[len('+++ b/'):] for l in patch.splitlines() if l.startswith('+++ b/')}
    assert inputs['upstream_commit'] == '17e99434af5ead3e989c08f32af33609821d0bc0'
    assert set(inputs['baseline']) == set(inputs['patched']) == patched_in_patch and len(patched_in_patch) == 18

    cmp = json.loads((HERE / 'comparison.json').read_text())
    raw = (HERE / 'token_metadata.so').read_bytes()
    assert sha(raw) == cmp['raw_compiler_output_sha256'] and len(raw) == cmp['raw_compiler_output_bytes'] == 707448
    assert cmp['source_patch_sha256'] == sha((HERE / 'source.patch').read_bytes())
    assert cmp['full_byte_equality'] is True and cmp['differing_positions'] == 0

    loc = json.loads((HERE / 'location-records.json').read_text())
    raw_locs = locations(raw)
    assert len(raw_locs) == loc['original_records'] == 287
    for r in loc['records_corrected_from_candidate11']:
        got = raw_locs[r['record_offset']]
        assert [got[1], got[2]] == r['exact_line_col'] == r['original_line_col'] != r['candidate11_line_col'], r

    result = {'status': 'PACKAGE_OK', 'files': len(listed), 'raw_sha256': sha(raw), 'location_records': len(raw_locs),
              'corrected_location_records': len(loc['records_corrected_from_candidate11'])}
    if not a.package_only:
        orig = (a.repo / 'evidence/dependencies/token_metadata/deployed.so').read_bytes()
        assert sha(orig) == cmp['captured_original_sha256'] == '31f0a627dba051a938de650464e55cc5397a4be0fd496929c1f9cf02fe5e9011'
        assert raw == orig[:len(raw)], 'raw compiler output differs from the captured ELF extent'
        tail = orig[len(raw):]
        assert len(tail) == 86543 and tail.count(0) == len(tail), 'captured allocation tail is not all zero'
        padded = raw + bytes(len(orig) - len(raw))
        assert padded == orig and sha(padded) == cmp['padded_candidate_sha256']
        assert locations(orig) == raw_locs
        result.update(status='BYTE_IDENTICAL', captured_bytes=len(orig), zero_padding=len(tail), differing_positions=0)
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    sys.exit(main())
