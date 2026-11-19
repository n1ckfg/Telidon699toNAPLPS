#!/usr/bin/env python3
"""Identify whether an input file is Telidon 699 or NAPLPS (709) format.

Usage:
    ./identify.py [-v | --verbose] <file> [<file> ...]

Outputs '699', 'naplps', or 'unknown' for each file.
"""

from dataclasses import dataclass, field
import argparse
import sys


SO = 0x0E   # Shift Out: enter PDI graphics mode (G1)
SI = 0x0F   # Shift In: enter text mode (G0)
CAN = 0x18  # NAPLPS: end macro processing
EM = 0x19   # Single-shift G2 (accents)
ESC = 0x1B  # NAPLPS: code extension / 7-bit C1 control
FS = 0x1C   # NAPLPS: set cursor position
GS = 0x1D   # NAPLPS: single-shift G3
RS = 0x1E   # NAPLPS: cursor home
US = 0x1F   # NAPLPS: non-selective reset (NSR)

# PDI opcodes that exist only in NAPLPS (unused/do-nothing or private in 699)
NAPLPS_ONLY_OPCODES = {
    0x20: 'RESET (SPC)',
    0x21: 'DOMAIN (!)',
    0x22: 'TEXT (")',
    0x23: 'TEXTURE (#)',
    0x3F: 'BLINK (?)',
}

# Geometric primitives shared identically by 699 and NAPLPS ($..7)
SHARED_GEOMETRY_OPCODES = set(range(0x24, 0x38))


@dataclass
class IdentificationResult:
    format: str  # '699', 'naplps', or 'unknown'
    score_699: int = 0
    score_naplps: int = 0
    reasons_699: list[str] = field(default_factory=list)
    reasons_naplps: list[str] = field(default_factory=list)
    note: str = ''


def identify_bytes(data: bytes) -> IdentificationResult:
    """Classify raw bytes as '699', 'naplps', or 'unknown'."""
    if not data:
        return IdentificationResult('unknown', note='empty file')

    # Both Telidon 699 and standard 7-bit NAPLPS use 7-bit ASCII bytes (0x00-0x7F).
    if any(b >= 0x80 for b in data):
        return IdentificationResult('unknown', note='contains non-7-bit bytes (>= 0x80)')

    score_699 = 0
    score_naplps = 0
    counts_699: dict[str, int] = {}
    counts_naplps: dict[str, int] = {}

    def add_699(label: str, weight: int) -> None:
        nonlocal score_699
        score_699 += weight
        counts_699[label] = counts_699.get(label, 0) + 1

    def add_naplps(label: str, weight: int) -> None:
        nonlocal score_naplps
        score_naplps += weight
        counts_naplps[label] = counts_naplps.get(label, 0) + 1

    in_pdi = False
    cur_op: int | None = None
    cur_ops: list[int] = []

    def flush_pdi() -> None:
        nonlocal cur_op, cur_ops
        if cur_op is None:
            return
        op = cur_op
        ops = cur_ops
        cur_op = None
        cur_ops = []

        if op in NAPLPS_ONLY_OPCODES:
            if ops:
                add_naplps(NAPLPS_ONLY_OPCODES[op], 10)
            return

        if op == 0x3D:  # '=': 699 Status vs NAPLPS WAIT
            if len(ops) >= 2 and 0x40 <= ops[0] <= 0x67:
                # NAPLPS WAIT takes at most 1 operand byte; multi-byte '=' is 699 Status
                # (e.g. =T/=U fill pattern, =` text format, =a text size).
                sub = chr(ops[0])
                add_699(f'699 status ={sub} (multi-byte)', 15)
            elif len(ops) == 1:
                sub_val = ops[0]
                if sub_val == 0x40:
                    # '=@' is ambiguous: 699 clear-to-black OR NAPLPS WAIT 0.
                    pass
                elif 0x41 <= sub_val <= 0x67:
                    add_699(f'699 status ={chr(sub_val)}', 5)
            return

        if op == 0x3C:  # '<': 699 Value (typically 1 byte) vs NAPLPS SET COLOUR (typically 3 bytes)
            if len(ops) == 1:
                add_699('1-byte < colour/value', 1)
            elif len(ops) == 3:
                add_naplps('3-byte < SET COLOUR', 1)

    i = 0
    n = len(data)
    while i < n:
        b = data[i]

        if b == SO:
            flush_pdi()
            in_pdi = True
            i += 1
            continue

        if b == SI:
            flush_pdi()
            in_pdi = False
            i += 1
            continue

        if b == ESC:
            flush_pdi()
            i += 1
            if i < n:
                nxt = data[i]
                if 0x40 <= nxt <= 0x5F:
                    # 7-bit C1 control (e.g. ESC D = DEF MACRO, ESC E = END)
                    add_naplps(f'ESC {chr(nxt)} (C1)', 10)
                    i += 1
                    # DEF MACRO / DEF P-MACRO / DEF T-MACRO / DEF DRCS take a 1-byte name
                    if nxt in (0x41, 0x42, 0x43, 0x44) and i < n and 0x40 <= data[i] <= 0x7F:
                        i += 1
                elif 0x20 <= nxt <= 0x2F:
                    # ISO 2022 designation sequence: intermediate bytes 0x20-0x2F + final 0x30-0x7E
                    add_naplps('ESC ISO-2022 sequence', 10)
                    while i < n and 0x20 <= data[i] <= 0x2F:
                        i += 1
                    if i < n and 0x30 <= data[i] <= 0x7E:
                        i += 1
                else:
                    add_naplps('ESC', 5)
            continue

        if b == US:
            flush_pdi()
            add_naplps('US (NSR)', 10)
            i += 1
            # NSR takes up to 2 operand bytes (0x40-0x7F)
            for _ in range(2):
                if i < n and 0x40 <= data[i] <= 0x7F:
                    i += 1
                else:
                    break
            in_pdi = False
            continue

        if b == EM:
            flush_pdi()
            # G2 single-shift: skip the single following character
            i += 2
            continue

        if b == CAN:
            flush_pdi()
            if in_pdi:
                add_naplps('CAN (end macro)', 5)
            i += 1
            continue

        if b in (FS, GS, RS):
            flush_pdi()
            if in_pdi:
                add_naplps(f'C0 0x{b:02X}', 3)
            i += 1
            continue

        if in_pdi:
            if b < 0x40:
                flush_pdi()
                if 0x20 <= b <= 0x3F:
                    cur_op = b
                    cur_ops = []
            else:
                if cur_op is not None:
                    cur_ops.append(b)
        i += 1

    flush_pdi()

    reasons_699 = [f'{k} x{v}' for k, v in sorted(counts_699.items())]
    reasons_naplps = [f'{k} x{v}' for k, v in sorted(counts_naplps.items())]

    if score_699 == 0 and score_naplps == 0:
        return IdentificationResult(
            'unknown',
            score_699=score_699,
            score_naplps=score_naplps,
            note='no distinguishing 699 or NAPLPS commands found',
        )

    if score_699 > score_naplps:
        fmt = '699'
    elif score_naplps > score_699:
        fmt = 'naplps'
    else:
        fmt = 'unknown'

    return IdentificationResult(
        fmt,
        score_699=score_699,
        score_naplps=score_naplps,
        reasons_699=reasons_699,
        reasons_naplps=reasons_naplps,
    )


def identify_file(path: str) -> IdentificationResult:
    with open(path, 'rb') as f:
        return identify_bytes(f.read())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description='Identify whether input file(s) are Telidon 699 or NAPLPS format.'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='show score breakdown and matched protocol features',
    )
    parser.add_argument('files', nargs='+', help='path(s) to input file(s)')
    args = parser.parse_args(argv)

    multi = len(args.files) > 1
    exit_code = 0

    for path in args.files:
        try:
            res = identify_file(path)
        except OSError as err:
            print(f'{path}: error: {err}', file=sys.stderr)
            exit_code = 1
            continue

        if res.format == 'unknown':
            exit_code = 1

        prefix = f'{path}: ' if multi else ''
        if not args.verbose:
            print(f'{prefix}{res.format}')
        else:
            details = [f'score_699={res.score_699}', f'score_naplps={res.score_naplps}']
            if res.note:
                details.append(res.note)
            if res.reasons_699:
                details.append('699=[' + ', '.join(res.reasons_699) + ']')
            if res.reasons_naplps:
                details.append('naplps=[' + ', '.join(res.reasons_naplps) + ']')
            print(f'{prefix}{res.format} ({"; ".join(details)})')

    return exit_code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
