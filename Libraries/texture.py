"""Convert a Telidon 699 fill pattern to its NAPLPS (709) texture equivalent.

Python port of Texture.pm (John Durno, 2019).

In 699, =T / =U specify hatching algorithmically: the first bit of X and Y
selects diagonal vs. orthogonal hatching and the next 4 bits give line
densities in 1/16 increments. This module synthesizes a 16x16 NAPLPS
programmable texture mask that approximates the pattern.
"""

import math
import sys

from .bitutil import byte_bits, pack_bits

DIMENSION = 16

ESC = b'\x1b'
SO = b'\x0e'


def texture(operands):
    """Convert 699 fill operands (raw bytes) to a NAPLPS texture.

    Returns a tuple (texture, masksize):
      * texture is None for empty operands, b'@' for a solid fill, or the
        NAPLPS macro that defines the texture mask bitmap;
      * masksize is the new mask size operand (e.g. b'@R@'), or None if the
        caller's current mask size should be left unchanged.
    """
    if not operands:
        return None, None

    x = ''
    y = ''
    for operand in operands:
        xy = byte_bits(operand)
        x += xy[2:5]
        y += xy[5:8]

    if x[1:5] == '1111':
        return b'@', None
    if y[1:5] == '1111':
        return b'@', None

    x_angle = x[0:1] == '1'  # 1 = slope at 45
    y_angle = y[0:1] == '1'  # 1 = slope at 135

    x_fill = _fill_stride(bin2dec(x[1:5]))  # max 4 bits precision (1/16)
    y_fill = _fill_stride(bin2dec(y[1:5]))

    def_texture = b''
    masksize = None
    grid = ''

    if not x_angle and not y_angle:
        # on a 16x16 grid, textures are:
        # @R@ - grid, @B@ - horizontal hatch, @P@ - vertical hatch
        if x_fill < 2 and y_fill < 2:  # no texture, solid fill
            return b'@', None
        elif x_fill < 2 and y_fill >= 2:  # horizontal fill
            masksize = b'@B@'
        elif x_fill >= 2 and y_fill < 2:  # vertical fill
            masksize = b'@P@'
        else:  # grid fill
            masksize = b'@R@'
        def_texture = def_texture_begin(masksize)
        grid = gridrect(x_fill, y_fill)
    elif x_angle and not y_angle:
        masksize = b'@R@'
        def_texture = def_texture_begin(masksize)
        grid = gridangle_y(x_fill)
    elif not x_angle and y_angle:
        masksize = b'@R@'
        def_texture = def_texture_begin(masksize)
        grid = gridangle_x(y_fill)
    else:
        print_stdout(b'GOT GRID ANGLE X AND Y!!:%d,%d\n' % (x_fill, y_fill))
        # Only the 50% case is handled; otherwise an empty macro body is emitted.
        if x_fill == 2 and y_fill == 2:
            masksize = b'@R@'
            def_texture = def_texture_begin(masksize)
            grid = gridangle_y(x_fill)

    # To pack as an encoding, 6 bits per byte.
    # On a 16x16 grid, 3 bytes (6+6+4) per line.
    num_bytes = math.ceil(DIMENSION / 6)
    zeros = num_bytes * 6 - DIMENSION
    usable = len(grid) - len(grid) % DIMENSION  # incomplete trailing rows are dropped
    for start in range(0, usable, DIMENSION):
        row = grid[start:start + DIMENSION] + '0' * zeros
        for i in range(num_bytes):
            def_texture += pack_bits('01' + row[i * 6:i * 6 + 6])

    def_texture += def_texture_end()
    return def_texture, masksize


def _fill_stride(dec):
    """Turn a density fraction into an integer stride, eg 0.5 = 2, every other space."""
    if dec == 0:
        return 0
    if dec > 0.5:
        dec = 1 - dec
    return int(1 / dec)


def gridrect(x_fill, y_fill):
    """Horizontal, vertical, or crosshatch grid."""
    grid = []
    for i in range(DIMENSION, 0, -1):  # rows
        for j in range(DIMENSION, 0, -1):  # columns
            if y_fill > 0 and i % y_fill == 0:
                grid.append('1')
            elif x_fill > 0 and j % x_fill == 0:
                grid.append('1')
            else:
                grid.append('0')
    return ''.join(grid)


def gridangle_y(fill):
    """Lines angled +135."""
    grid = []
    num_zeros = fill - 1
    for _ in range(DIMENSION):  # rows
        if num_zeros < 0:
            num_zeros = fill - 1
        grid.append('0' * max(num_zeros, 0))
        for j in range(DIMENSION, num_zeros, -1):  # columns
            grid.append('1' if fill > 0 and j % fill == 0 else '0')
        num_zeros -= 1
    return ''.join(grid)


def gridangle_x(fill):
    """Lines angled -45."""
    grid = []
    rownum = 0
    for _ in range(DIMENSION):  # rows
        if rownum == fill:
            rownum = 0
        else:
            grid.append('0' * rownum)
        for j in range(DIMENSION, rownum, -1):  # columns
            grid.append('1' if fill > 0 and j % fill == 0 else '0')
        rownum += 1
    return ''.join(grid)


def def_texture_begin(pelsize):
    """Start of the macro that draws the texture mask bitmap.

    @R@ !I<pelsize>  - mask size and domain
    ESC D A          - define macro A
    8$ 9A            - incremental point ... ('A' is needed, not sure why)
    """
    return b'@R@!I' + pelsize + ESC + b'DA8$9A'


def def_texture_end():
    """End of macro definition, then restore default domain and solid texture."""
    return ESC + b'E' + SO + b'!H@@I#@'


def bin2dec(bits):
    """Convert a binary fraction string to its decimal equivalent."""
    result = 0.0
    divide_by = 2
    for digit in bits:
        result += int(digit) / divide_by
        divide_by *= 2
    return result


def print_stdout(data):
    """Write raw bytes to stdout (the Perl original printed operand bytes verbatim)."""
    sys.stdout.buffer.write(data)
