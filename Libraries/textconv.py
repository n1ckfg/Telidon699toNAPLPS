"""Convert Telidon 699 text attributes to NAPLPS equivalents.

Python port of Textconv.pm (John Durno, 2019).

699 only has 8 character sizes, from biggest (0) to smallest (7), expressed
as fractions of the screen. NAPLPS uses a continuous character field size,
so the values below are empirically tuned approximations.
"""

from dataclasses import dataclass

from .bitutil import byte_bits, pack_bits, perl_num_str

# x values indicate number of chars per line;
# slightly more than spec, so chars are slightly smaller, don't go right to edge.
#
# saved values:
# XVALUES = (24, 34, 52, 60, 90, 120, 160, 260)
# DISP = (0, -1.4, -2.1, -2, 0, 0, 0, 0)
# DISP_DOUBLE = (1.5, 1.4, 0.6, 0.1, 0, 0, 0, 0)

XVALUES = (26, 36, 54, 72, 96, 128, 180, 260)
DISP = (1.5, 1.2, 1, 0.8, 0, 0, 0, 0)
DISP_DOUBLE = (1.5, 1.4, 1.2, 1.2, 0, 0, 0, 0)

DISPLACEMENT = 1 / 8

# 699 vertical spacing (1, 1.5, 2, 2.5) -> NAPLPS (1, 1.25, 1.5, 2).
# Sadly NAPLPS replaces 2.5 with 1.25, so the values are not the same.
INTERNARROW = {
    '00': '00',
    '01': '10',
    '10': '11',
    '11': '11',
}


@dataclass
class TextState:
    """Text-size state shared between textsize() and the displacement functions."""

    numeric: int = 0        # current text size index supplied by the PDI
    double: bool = False    # is the current text double height?
    y_dec: float = 0.0      # y value of the current text size, in decimal


def _operand_bits(pdi):
    """Bits of the first operand byte (third byte) of a status PDI, or '' if absent."""
    return byte_bits(pdi[2]) if len(pdi) > 2 else ''


def textsize(pdi, state):
    """Convert a 699 text size PDI (=a) to a 3-byte NAPLPS size operand."""
    bits = _operand_bits(pdi)
    state.double = bits[2:3] == '1'
    size_bits = bits[5:8]
    size = int(size_bits, 2) if size_bits else 0
    state.numeric = size  # remember the index value of the current text size

    x = '%.7f' % (1 / XVALUES[size])
    y = float('%.7f' % ((1 + 3 / 8) * float(x)))  # char height a proportion of width
    if state.double:
        y = y * 2

    state.y_dec = y
    return dec2pdi(float(x), y)


def textformat(pdi):
    """Convert a 699 text format PDI (=`) to a 2-byte NAPLPS TEXT format operand."""
    bits = _operand_bits(pdi)
    # free_format = bits[2:3]  # 0=terminal, 1=diagram
    # word_break = bits[3:4]   # 0=char, 1=word
    rotation = bits[4:6]       # 00=normal, 01=down etc
    vertical = bits[6:8]       # 1, 1.5, 2, 2.5

    byte1 = '011100' + rotation
    byte2 = '010000' + INTERNARROW.get(vertical, '')
    return pack_bits(byte1) + pack_bits(byte2)


def _disp_height(state):
    table = DISP_DOUBLE if state.double else DISP
    return table[state.numeric]


def get_displacement_neg(state):
    """Relative point PDI that shifts the baseline down when entering text mode."""
    disp_height = _disp_height(state)
    displace_y = state.y_dec * (DISPLACEMENT * disp_height)

    # positive displacement if disp_height is negative
    if disp_height > 0:
        displace_y = 1.002 - displace_y  # not sure why it needs to be slightly more than one
    else:
        displace_y = displace_y * -1

    return b'%' + dec2pdi(0, displace_y)


def get_displacement_pos(state):
    """Relative point PDI that undoes get_displacement_neg() when leaving text mode."""
    disp_height = _disp_height(state)
    displace_y = state.y_dec * (DISPLACEMENT * disp_height)

    # negative displacement if disp_height is negative
    if disp_height < 0:
        displace_y = displace_y * -1
        displace_y = 1.002 - displace_y

    return b'%' + dec2pdi(0, displace_y)


def _chunks(text, size):
    return [text[i:i + size] for i in range(0, len(text), size)]


def dec2pdi(x, y):
    """Encode an (x, y) pair of fractions as three interleaved NAPLPS operand bytes."""
    array_x = _chunks(dec2bin(x), 3)
    array_y = _chunks(dec2bin(y), 3)

    encoded = b''
    for i in range(3):
        cx = array_x[i] if i < len(array_x) else ''
        cy = array_y[i] if i < len(array_y) else ''
        encoded += pack_bits('01' + cx + cy)
    return encoded


def dec2bin(dec):
    """Convert a fraction to 9 binary digits by repeated doubling.

    This mirrors the Perl original exactly: each step stringifies dec*2 and
    splits it on '.', taking the integer part as the "digit" and the rest as
    the remaining fraction. For values >= 1 (e.g. 1.002) the first digit can
    be '2', and pack_bits() later reads that as bit 0, just as Perl's pack does.
    """
    bits = ''
    for _ in range(9):
        parts = perl_num_str(dec * 2).split('.')
        bits += parts[0]
        dec = float('0.' + (parts[1] if len(parts) > 1 else ''))
    return bits
