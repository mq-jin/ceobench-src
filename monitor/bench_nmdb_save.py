"""Benchmark the cost of save_session_db / load_session_db on a live-size DB.

Times every phase of the encrypt/decrypt pipeline to pinpoint the bottleneck.
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Load .env
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from saas_bench.db_protection import (
    _decrypt,
    _encrypt,
    _aes_ctr_keystream,
    _xor_bytes,
    _derive_key,
    load_session_db,
    save_session_db,
    protect_db,
    unprotect_db,
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--nmdb", required=True, help="Path to .nmdb file to benchmark")
    p.add_argument("--runs", type=int, default=3)
    args = p.parse_args()

    nmdb_path = Path(args.nmdb)
    size_mb = nmdb_path.stat().st_size / 1e6
    print(f"[bench] nmdb path: {nmdb_path}")
    print(f"[bench] nmdb size: {size_mb:.1f} MB")

    # 1) Load it (full load_session_db path)
    print("\n[bench] === load_session_db (full) ===")
    for i in range(args.runs):
        t0 = time.monotonic()
        conn = load_session_db(nmdb_path)
        elapsed = time.monotonic() - t0
        print(f"  run {i+1}: {elapsed:.2f}s")
        if i < args.runs - 1:
            conn.close()

    # Keep last conn for save benchmarks
    # 2) Raw _decrypt
    print("\n[bench] === _decrypt (raw) ===")
    data = nmdb_path.read_bytes()
    for i in range(args.runs):
        t0 = time.monotonic()
        plaintext = _decrypt(data)
        elapsed = time.monotonic() - t0
        print(f"  run {i+1}: {elapsed:.2f}s  ({len(plaintext)/1e6:.1f} MB plaintext)")

    # 3) Raw _encrypt
    print("\n[bench] === _encrypt (raw) ===")
    for i in range(args.runs):
        t0 = time.monotonic()
        ciphertext = _encrypt(plaintext)
        elapsed = time.monotonic() - t0
        print(f"  run {i+1}: {elapsed:.2f}s")

    # 4) _aes_ctr_keystream alone
    print("\n[bench] === _aes_ctr_keystream alone ===")
    full_key = _derive_key()
    enc_key = full_key[:32]
    nonce = os.urandom(16)
    for i in range(args.runs):
        t0 = time.monotonic()
        ks = _aes_ctr_keystream(enc_key, nonce, len(plaintext))
        elapsed = time.monotonic() - t0
        print(f"  run {i+1}: {elapsed:.2f}s  ({len(ks)/1e6:.1f} MB keystream)")

    # 5) _xor_bytes alone
    print("\n[bench] === _xor_bytes alone ===")
    for i in range(args.runs):
        t0 = time.monotonic()
        out = _xor_bytes(plaintext, ks)
        elapsed = time.monotonic() - t0
        print(f"  run {i+1}: {elapsed:.2f}s")

    # 6) save_session_db (full)
    print("\n[bench] === save_session_db (full) ===")
    tmp_out = nmdb_path.parent / "bench_save_tmp.nmdb"
    try:
        for i in range(args.runs):
            t0 = time.monotonic()
            save_session_db(conn, tmp_out)
            elapsed = time.monotonic() - t0
            print(f"  run {i+1}: {elapsed:.2f}s  ({tmp_out.stat().st_size/1e6:.1f} MB written)")
    finally:
        if tmp_out.exists():
            tmp_out.unlink()
    conn.close()


if __name__ == "__main__":
    main()
