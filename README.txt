Convert Telidon 699 to NAPLPS

Notes:
	-Converter is not complete, a number of opcodes not implemented
	-Textures do not always work, and are not always accurate
	-Font scaling is pretty good, but not perfect

Instructions:

Put a folder of Telidon 699 graphics files the same directory as the conversion program (699toNAPLPS.pl)

Run the script 699toNAPLPS.pl to convert the files to NAPLPS format
eg. ./699toNAPLPS.pl samples

This will create a copy of the folder in a directory called NAPLPS containing the converted files.
A diagnostic log is written to logfile.txt.

Note: Perl 5.26 and later no longer search the current directory for modules,
so run the Perl version as: perl -I. 699toNAPLPS.pl samples

Python version:

699toNAPLPS.py is a Python 3 port (no dependencies beyond the standard library)
that produces byte-identical output, log, and console messages.
eg. ./699toNAPLPS.py samples

The Python modules live alongside the Perl ones in Libraries/
(textconv.py, texture.py, and bitutil.py for Perl pack/stringify compatibility).

