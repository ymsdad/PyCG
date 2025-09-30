# Summary of Modifications to PyCG

This file summarizes the changes made to the original PyCG source code, grouped by feature. As per the Apache 2.0 License, prominent notices have also been added to the top of each modified file.

---

### Feature: Whitelist for File Analysis

A `files_whitelist` feature was added to control which files are included in the call graph analysis, with improved logic to handle module names for compiled shared objects.

**Relevant Files:**
- `pycg/pycg.py`
- `pycg/machinery/imports.py`
- `pycg/processing/base.py`
- `pycg/processing/preprocessor.py`
- `pycg/utils/common.py`

---

### Feature: Positional-Only Argument Support

Support was added to correctly handle default values for positional-only arguments in function definitions.

**Relevant Files:**
- `pycg/processing/preprocessor.py`