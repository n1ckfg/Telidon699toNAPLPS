Convert Telidon 699 to NAPLPS

Python 3 port of the original Perl converter (John Durno, 2019), with no
dependencies beyond the Python standard library.

Notes:
	- Converter is not complete; a number of opcodes are not implemented
	- Textures do not always work, and are not always accurate
	- Font scaling is pretty good, but not perfect

Instructions:

1. Convert a directory of Telidon 699 graphics files using 699toNAPLPS.py:

   ./699toNAPLPS.py samples/699

   Each valid 699 file is converted and written with a .nap extension under
   NAPLPS/<indir>/, with a diagnostic log written to logfile.txt. Non-699
   files (including NAPLPS, plain text, or binary files) are automatically
   skipped using identify.py.

2. Batch convert into a specific output directory using batch_convert.sh:

   ./batch_convert.sh [input_dir] [output_dir] [log_file]

   With no arguments, this converts samples/699 into samples/naplps and
   writes logfile.txt in the repository root.

3. Identify whether files are Telidon 699 or NAPLPS format using identify.py:

   ./identify.py [-v] <file> [<file> ...]

Modules:

The support modules live in the repository root alongside 699toNAPLPS.py:
	- textconv.py  (699 text size/format and baseline conversion)
	- texture.py   (699 fill pattern to NAPLPS programmable texture synthesis)
	- bitutil.py   (bit-packing and numeric formatting helpers)
	- identify.py  (Telidon 699 vs. NAPLPS format detection)
