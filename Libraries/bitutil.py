"""Bit-string helpers that reproduce the Perl built-ins the original converter relied on.

The Perl code works on strings of '0'/'1' characters, converting with
``unpack("B*", ...)`` and ``pack("B*", ...)``. These helpers keep those
semantics, including the corner cases, so the Python port produces
byte-identical output.
"""


def byte_bits(value):
    """Return the 8-character binary string of a byte, like Perl's unpack("B*", $char)."""
    return format(value, '08b')


def pack_bits(bits):
    """Pack a string of bit characters into bytes, like Perl's pack("B*", $bits).

    As in Perl, each character contributes the low bit of its ordinal value
    (so '0' -> 0 and '1' -> 1, but also e.g. '2' -> 0), and a trailing partial
    byte is padded with zero bits.
    """
    out = bytearray()
    acc = 0
    count = 0
    for ch in bits:
        acc = (acc << 1) | (ord(ch) & 1)
        count += 1
        if count == 8:
            out.append(acc)
            acc = 0
            count = 0
    if count:
        out.append(acc << (8 - count))
    return bytes(out)


def perl_num_str(value):
    """Stringify a float the way Perl stringifies a numeric value (NV).

    Perl prints NVs with 15 significant digits ("%.15g") and prints both
    0.0 and -0.0 as "0".
    """
    if value == 0:
        return '0'
    return '%.15g' % value
