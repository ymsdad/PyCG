# CppCG - Practical C Call Graphs

[![Linters](https://github.com/vitsalis/PyCG/actions/workflows/linters.yml/badge.svg)](https://github.com/vitsalis/PyCG/actions/workflows/linters.yml)
[![Tests](https://github.com/vitsalis/PyCG/actions/workflows/test.yaml/badge.svg)](https://github.com/vitsalis/PyCG/actions/workflows/test.yaml)

CppCG generates call graphs for C code using static analysis. It is designed to handle the complexities of the C language to produce as precise as possible call graphs.

The methodology is heavily inspired by PyCG. For a detailed explanation of the original Python-based approach, please see the [ICSE 2021 paper](https://arxiv.org/pdf/2103.00587.pdf).

For a detailed explanation of this project's architecture and design, please see [STRUCTURE.md](STRUCTURE.md).

The formal semantics of the analysis are specified in LaTeX format in the `drafts/analysis_rules.tex` file.

# Usage

```
~ >>> cppcg -h
usage: main.py [-h] [--package PACKAGE] [--product PRODUCT]
               [--forge FORGE] [--version VERSION] [--timestamp TIMESTAMP]
               [--max-iter MAX_ITER] [--as-graph-output AS_GRAPH_OUTPUT]
               [-o OUTPUT] [entry_point ...]

...
```

# Examples

To analyze a set of C files and generate a call graph in JSON format:
```
~ >>> cppcg --package my_project $(find my_project -type f -name "*.c") -o cg.json
```

# Running Tests

From the root directory, simply run the tests by executing:
```
pytest
```
