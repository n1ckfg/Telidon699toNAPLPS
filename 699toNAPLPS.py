#!/usr/bin/env python3
"""Convert Telidon 699 PDIs to 709/NAPLPS.

Python port of 699toNAPLPS.pl (John Durno, 2019).

Usage: ./699toNAPLPS.py <indir>

Every file in <indir> is converted and written to NAPLPS/<indir>/, with a
diagnostic log in logfile.txt. Output is byte-identical to the Perl original.
"""

import os
import sys

import textconv, texture
from bitutil import byte_bits

OUTDIR = 'NAPLPS'
LOGFILE = 'logfile.txt'

SO = 0x0E  # shift out: exit text mode
SI = 0x0F  # shift in: enter text mode
CR = 0x0D

# ASCII bytes that do nothing (in 699)
DO_NOTHING = {
    0x00: 'NUL', 0x01: 'SOH', 0x02: 'STX', 0x03: 'ETX',
    0x04: 'EOT', 0x05: 'ENQ', 0x06: 'ACK',
    0x10: 'DLE', 0x11: 'DC1', 0x12: 'DC2', 0x13: 'DC3',
    0x14: 'DC4', 0x15: 'NAK', 0x16: 'SYN', 0x17: 'ETB',
    0x18: 'CAN', 0x1A: 'SUB', 0x1B: 'ESC', 0x1C: 'FS',
    0x1D: 'GS', 0x1E: 'RS', 0x1F: 'US',
    0x20: 'Space', 0x21: '!', 0x22: 'Double Quote', 0x23: '#',
    0x3F: '?', 0x3E: '>',
}

# PDI opcodes copied to the output unchanged.
PASSTHROUGH = {
    0x07,  # BEL  ring a bell
    0x08,  # BS   reset back one char width
    0x09,  # HT   reset forward one tab (default one space)
    0x0A,  # LF   reset to current x, down one line
    0x0B,  # VT   raise Y coord one tab (default 1 char height)
    0x0C,  # FF   clear screen, reset to left margin & y one char down (not sure about this one)
    0x0D,  # CR   reset to margin x, current y
    0x0F,  # SI   enter text mode
    0x19,  # EM   invoke g2 chars (accents)
    0x25,  # %    point, relative invisible
    0x26,  # &    point, absolute visible
    0x27,  # '    point, relative visible
    0x28,  # (    line, absolute
    0x29,  # )    line, relative
    0x2A,  # *    set & line (absolute)
    0x2B,  # +    set & line (relative)
    0x2C,  # ,    arc, outline
    0x2D,  # -    arc, filled
    0x2E,  # .    set & arc (outline)
    0x2F,  # /    set & arc (filled)
    0x30,  # 0    rectangle, outlined
    0x31,  # 1    rectangle, filled
    0x32,  # 2    set & rectangle (outlined)
    0x33,  # 3    set & rectangle (filled)
    0x34,  # 4    polygon (outlined)
    0x35,  # 5    polygon (filled)
    0x36,  # 6    set & polygon (outlined)
    0x37,  # 7    set & polygon (filled)
}

# Bit format opcodes (not implemented); reported on stdout.
BIT_FORMATS = {
    0x38: b'GOT 8\teight\tbit format 0\n',
    0x39: b'GOT 9\tnine\tbit format 1\n',
    0x3A: b'GOT :\tcolon\tSet & bit format 0\n',
    0x3B: b'GOT ;\tsemicolon\tSet & bit format 1\n',
}

# Status commands (=<x>) that are only logged, keyed by sub-opcode.
STATUS_LOG_ONLY = {
    b'A': b'got =A, clear screen, set transparent\n',
    b'D': b"GOT '=D' domain 9bits,3bytes (default)\n",
    b'E': b"***GOT '=E' domain 12bits,4bytes***\n",
    b'F': b"***GOT '=F' domain 15bits,5bytes***\n",
    b'G': b"***GOT '=G' domain 18bits,6bytes***\n",
    b'I': b'GOT =I #BLINK: blink off, trans on\n',
    b'J': b'GOT =J/ #BLINK: blink on, trans off\n',
    b'K': b'GOT =K #BLINK: blink on, trans on\n',
    b'V': b'GOT =V #fill black highlight\n',
    b'W': b'GOT =W #fill (reserved)\n',
    b'X': b'GOT =X #marker off, reposition\n',
    b'Y': b'GOT =Y #marker on, reposition\n',
    b'Z': b'GOT =Z #marker (specified) off, repos\n',
    b'[': b'GOT =[ #marker (specified) off, repos\n',
    # wait timed: delay is one or two bytes, least to most significant, tenths of a second
    b'\\': b'GOT = #wait timed\n',
    b']': b'GOT =] #wait indefinite\n',
    b'^': b'GOT =^/ #wait timed flow control\n',
    b'_': b'GOT =_ #wait indefinite flow control\n',
    b'b': b'GOT =b #character set\n',
    b'c': b'GOT =c #tab positions',
}

# Status commands with a fixed NAPLPS translation.
STATUS_FIXED = {
    b'@': b'\x20\x78\x7f',  # RESET to black: SPC (selective reset), x (border & main to black), DEL
    b'H': b'?@@@',          # BLINK: blink off, trans off
    b'P': b'#@',            # LINE CONTROL: solid line
    b'Q': b'#A',            # LINE CONTROL: dotted line
    b'R': b'#B',            # LINE CONTROL: dashed line
    b'S': b'#C',            # LINE CONTROL: dotted-dashed line
}
STATUS_FIXED_LOG = {
    b'H': b'GOT =H #BLINK: blink off,trans off\n',
    b'P': b'GOT =P #LINE CONTROL: solid line\n',
    b'Q': b'GOT =Q #LINE CONTROL: dotted line\n',
    b'R': b'GOT =R #LINE CONTROL: dashed line\n',
    b'S': b'GOT =S #LINE CONTROL: dotted-dashed line\n',
}

# NAPLPS bootstrap sequence emitted at the start of the first file and on =B.
INITIALIZE_PDI = bytes([
    0x0E,              # SO
    0x18,              # CAN: end all macro processing
    0x1F, 0x40, 0x40,  # US @@: non-selective reset, reposition cursor to upper left
    0x0E,              # SO
    0x3D, 0x40,        # =@: wait zero
    0x20, 0x7B, 0x4F,  # SPC {O: selective reset
    0x21, 0x48,        # !H: domain, 1 single-value op, 3 multi-value op, 2D
    0x40, 0x40, 0x49,  # @@I: size of logical pel (smallest possible)
    0x0F,              # SI
    0x0E,              # SO
    0x23, 0x40, 0x40, 0x40,  # #@@@: set texture
])

# The four NAPLPS programmable texture masks. Only the first is used: other
# masks were not working with the decoders tested (2019-07-01).
TEXTURE_MASKS = (b'`', b'h', b'p', b'x')
ACTIVE_TEXTURE_MASKS = (b'`',)


def write_stdout(data):
    sys.stdout.buffer.write(data)


class Converter:
    """Converts 699 byte streams to NAPLPS.

    State that the Perl original kept in globals lives here. Some of it is
    reset for every file and some (text size/format, mask size, the current
    colour) deliberately carries over from one file to the next, as it did
    in the original.
    """

    def __init__(self, log):
        self.log = log

        self.converted = b''        # output since the most recent point abs invisible ($)
        self.fully_converted = b''  # output committed before that

        self.textmode = False       # False = PDI, True = text
        self.colourmode = True      # False = grey scale, True = colour
        self.current_colour = None
        self.current_position = b''  # current drawing point as a PDI

        self.text_state = textconv.TextState()
        self.current_textsize = b'@Az'
        self.current_textformat = b'p@'
        self.displacement_flag = False  # restore displacement on next shift out

        self.masksize = b'@R@'      # mask size for textures
        self.textures = {}          # mask label -> registered 699 fill operands
        self.last_saved_texture = b''

    # -- dispatch ---------------------------------------------------------

    def convert699(self, pdi):
        """Take a single PDI and decide how to process it."""
        if self.textmode:
            self.log(b'textmode: not a PDI: ' + pdi + b'\n')
        elif pdi.startswith(b'='):
            self.status_cmds(pdi)
        else:
            self.pdi_cmds(pdi)

    def status_cmds(self, pdi):
        """Convert PDI status commands (begin with '=')."""
        sub = pdi[1:2]

        if sub in STATUS_FIXED:
            self.converted += STATUS_FIXED[sub]
            if sub in STATUS_FIXED_LOG:
                self.log(STATUS_FIXED_LOG[sub])
        elif sub in STATUS_LOG_ONLY:
            self.log(STATUS_LOG_ONLY[sub])
        elif sub == b'B':  # RESET: clear to black, initialize
            self.initialize_pdi()
            self.log(b'=B #RESET: clear to black, initialize\n')
        elif sub == b'C':  # RESET: clear to current colour
            # SPC (selective reset), h (border & main to current colour), DEL
            self.converted += b'\x20\x68\x7f'
            self.log(b'=C #RESET: clear to current colour\n')
        elif sub in (b'L', b'N'):  # TONAL CONTROL: colour mode (bit b2 reserved)
            self.set_colourmode(True)
            self.log(b'colour mode\n')
        elif sub in (b'M', b'O'):  # TONAL CONTROL: grey scale mode (bit b2 reserved)
            self.set_colourmode(False)
            self.log(b'greyscale mode\n')
        elif sub == b'T':  # FILL: fill no highlight (outline)
            self.fill(pdi, b'T')
        elif sub == b'U':  # FILL: fill colour highlight
            self.fill(pdi, b'U')
        elif sub == b'`':  # text format
            self.log(b'GOT =` #text format: ' + pdi + b'\n')
            self.current_textformat = textconv.textformat(pdi)
            init = b'"' + self.current_textformat + self.current_textsize
            self.log(b'converted to ' + init + b'\n')
            self.converted += init
        elif sub == b'a':  # text size
            self.log(b'GOT =a #text size: ' + pdi + b'\n')
            self.current_textsize = textconv.textsize(pdi, self.text_state)
            init = b'"' + self.current_textformat + self.current_textsize
            self.log(b'Converted to ' + init + b'\n')
            self.converted += init
        elif sub in (b'd', b'e', b'f', b'g'):  # char def (reserved)
            self.log(b'got reserved PDI! ' + pdi + b'\n')
        else:
            self.log(b'got unrecognized PDI status code! ' + pdi + b'\n')

    def set_colourmode(self, colour):
        self.colourmode = colour
        # needed because the mode can change the current colour without setting it again
        if self.current_colour is not None:
            self.setcolour(self.current_colour)

    def fill(self, pdi, kind):
        """Convert a 699 fill pattern (=T or =U) to a NAPLPS texture."""
        init = b'#'
        tex = None
        fill = pdi[2:]  # the fill pattern part of the PDI (everything after '=T')
        if not fill:
            self.log(b'Got empty fill\n')
        else:
            tex, masksize = texture.texture(fill)
            if masksize is not None:
                self.masksize = masksize

        if tex == b'@':  # default textures are passed through
            init += tex
            self.log(b'GOT ' + tex + b' in passthrough mode\n')
        elif tex:
            init += self.register_texture(fill, tex) + self.masksize
        else:
            init = b''  # =T opcode with no operands is ignored

        self.log(b'GOT =' + kind + b' #fill no highlight (outline): ' + pdi + b'\n')
        self.log(b'Converted to: ' + init + b'\n')
        self.converted += init

    def register_texture(self, fill, tex):
        """Find or allocate a mask slot for a custom texture; return its label.

        New texture definitions go into fully_converted, i.e. before the most
        recent point abs invisible, because the macro moves the drawing cursor.
        """
        mask_label = None
        for mask in ACTIVE_TEXTURE_MASKS:
            registered = self.textures.get(mask)
            if registered == fill:  # already registered, use that mask
                mask_label = mask
                self.log(b'mask is still ' + mask + b'; texture is still #' + mask + tex + b'\n')
                break
            if not registered:  # blank mask, register it
                mask_label = mask
                self.textures[mask] = fill
                self.fully_converted += b'#' + mask + tex
                self.last_saved_texture = mask
                self.log(b'mask is now ' + mask + b'; texture is #' + mask + tex + b'\n')
                break

        if mask_label is None:
            # All slots are full, so replace the oldest mask. With a single
            # active slot, that is always the one just used.
            mask = self.last_saved_texture
            mask_label = mask
            self.textures[mask] = fill
            self.fully_converted += b'#' + mask + tex
            self.last_saved_texture = mask
            self.log(b'mask is now ' + mask + b'; texture is ' + tex + b'\n')

        write_stdout(b'before: ' + fill + b'\n')
        write_stdout(b'after: ' + mask_label + b' + ' + self.masksize + b'\n')
        return mask_label

    def pdi_cmds(self, pdi):
        """Convert graphics primitives, colour, and C0 controls."""
        opcode = pdi[0]

        if opcode in PASSTHROUGH:
            self.converted += pdi
        elif opcode == SO:  # exit text mode
            self.converted += pdi
            if self.displacement_flag:
                self.converted += textconv.get_displacement_pos(self.text_state)
                self.displacement_flag = False
        elif opcode == 0x24:  # $  point, absolute invisible
            self.current_position = pdi
            self.fully_converted += self.converted
            self.converted = pdi
        elif opcode in BIT_FORMATS:
            write_stdout(BIT_FORMATS[opcode])
        elif opcode == 0x3C:  # <  PDI control - value
            # Sets the colour (or greyscale). Assumes only the first three colour
            # bits of the first operand are significant; the standard says
            # 3-bit colour was a "typical system" (p42).
            self.setcolour(pdi)
            self.current_colour = pdi  # remember for later
        else:
            self.log(b'Got unrecognized opcode in PDI! ' + pdi + b'\n')

    def setcolour(self, pdi):
        if len(pdi) <= 1:
            return
        bits = byte_bits(pdi[1])  # first operand
        if self.colourmode:
            colour = int('01' + bits[2:5] * 2, 2)
            self.converted += b'<' + bytes([colour] * 3)
        else:
            b1, b2, b3 = bits[2], bits[3], bits[4]
            first = bytes([int('01' + b1 * 3 + b2 * 3, 2)])
            second = bytes([int('01' + b3 * 3 + b1 * 3, 2)])
            third = bytes([int('01' + b2 * 3 + b3 * 3, 2)])
            self.converted += b'<' + first + second + third
            self.log(b'grey scale: ' + first + b' ' + second + b' ' + third + b'\n')

    def initialize_pdi(self):
        self.converted += INITIALIZE_PDI

    # -- text mode helpers ------------------------------------------------

    def convert_newline(self):
        """Newlines require PDIs to set the left margin."""
        newline = b'\x0e%' + self.get_current_x() + b'\x0f'  # SO, point rel invisible, x, SI
        self.log(b'Newline: ' + newline + b'\n')
        return newline

    def get_current_x(self):
        """The x coord of the current position, for text positioning on newlines."""
        coords = self.current_position[1:]
        self.log(b'got coords: ' + coords + b'\n')
        x = b''
        for byte in coords:
            bits = byte_bits(byte)
            self.log(b'got byte: ' + bits.encode() + b'\n')
            x += bytes([int('01' + bits[2:5] + '000', 2)])
        return x

    # -- per file ---------------------------------------------------------

    def convert_file(self, data, first_file):
        """Convert one 699 file's bytes and return the NAPLPS bytes."""
        self.fully_converted = b''
        self.converted = b''
        if first_file:
            self.initialize_pdi()

        self.textmode = False
        self.colourmode = True
        self.current_position = b''
        self.textures = {}

        pdi = None
        for value in data:
            byte = bytes([value])

            # set text mode on or off
            if value == SI:
                if not self.textmode:
                    if pdi is not None:  # clear previous opcode
                        self.convert699(pdi)
                        pdi = None
                    self.textmode = True
                    self.converted += textconv.get_displacement_neg(self.text_state)
                    self.log(b'textmode is on\n')
                    self.displacement_flag = True
                else:
                    self.log(b'got textmode on but textmode already on\n')
            elif value == SO:
                if self.textmode:
                    self.textmode = False
                    self.log(b'textmode is off\n')
                else:
                    self.log(b'got textmode off but textmode already off\n')

            if self.textmode:
                self.log(b'textmode: ' + byte + b'\n')
                self.converted += byte
                # newlines need the left margin set after the carriage return
                if value == CR:
                    self.converted += self.convert_newline()
                continue

            if value < 0x40:  # opcodes always have 0 in the 7th bit
                if pdi is not None:
                    self.convert699(pdi)
                pdi = None
                # only start a new PDI if the incoming opcode is one we recognize
                if value not in DO_NOTHING:
                    pdi = byte
                elif value != 0x00:
                    self.log(b'got bad opcode! ' + DO_NOTHING[value].encode() + b'\n')
            elif pdi is not None:  # operand
                pdi += byte
            else:
                self.log(b'got operand ' + byte + b' but opcode not defined!\n')

        # process last pdi, if any
        if pdi is not None:
            self.convert699(pdi)

        # tack on a SUB char (sometimes needed so the last opcode will run)
        return self.fully_converted + self.converted + b'\x1a'


def list_input_files(indir):
    """Files in indir, sorted like Perl's glob("$indir/*") (case-insensitive, then ASCII)."""
    names = [n for n in os.listdir(os.fsencode(indir)) if not n.startswith(b'.')]
    names.sort(key=lambda n: (n.lower(), n))
    prefix = os.fsencode(indir) + b'/'
    return [prefix + n for n in names]


def main(argv):
    if len(argv) != 2:
        sys.stderr.write('usage: %s <indir>\n' % argv[0])
        return 2
    indir = argv[1]

    # put the converted files in a directory
    try:
        os.makedirs(OUTDIR + '/' + indir, exist_ok=True)
    except OSError as err:
        print("Couldn't create %s/%s: %s" % (OUTDIR, indir, err))
        return 1

    with open(LOGFILE, 'wb') as logfile:
        converter = Converter(logfile.write)
        filecount = 0
        for path in list_input_files(indir):
            filecount += 1

            # skip com.text files
            if path.endswith(b'text'):
                logfile.write(b'skipping ' + path + b'\n')
                continue
            write_stdout(path + b'\n')

            logfile.write(b'-------------' + path + b'-------------\n\n')
            data = b''
            if not os.path.isdir(path):
                with open(path, 'rb') as infile:
                    data = infile.read()

            output = converter.convert_file(data, first_file=(filecount == 1))
            with open(os.fsencode(OUTDIR) + b'/' + path + b'.nap', 'wb') as outfile:
                outfile.write(output)

    write_stdout(b'\nAll done\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
