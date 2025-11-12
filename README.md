# Jambiato

Checker for tracking graypaper equations' modifications.
Brought to you by Davide Gessa (dakk), developer of JamPy.

## Tagging your source code

Your source code should have comments containing equation numbers in this format (spaces are optional):

```$(VERSION - EQUATION_NUMBER)```

for instance:

```$(0.4.5 - 123)```

If a block of code implements multiple equations, use \ separators:

```$(VERSION - EQ1 \ EQ2 \ E3)```


## Run Jambiato

```bash
python jambiato.py YOUR_SOURCE_DIRECTORY
```

```
usage: Jambiato [-h] [-nu] [-e EXTENSIONS] code_path

Checker for tracking graypaper equations' modifications

positional arguments:
  code_path

options:
  -h, --help            show this help message and exit
  -nu, --no-update
  -e, --extensions EXTENSIONS
                        file extensions of the code, comma separated (for instance: 'py,pyx')
```


## License

This software is licensed with [Apache License 2.0](LICENSE).