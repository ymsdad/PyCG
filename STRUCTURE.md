# Project Structure and Design

CppCG performs a multi-pass analysis on the C source code. It uses the `tree-sitter` library to parse the code into a concrete syntax tree and then traverses this tree multiple times to build up the information needed for call graph generation.

## Multi-Pass Architecture

The analysis is broken down into a 3-pass pipeline, with data-flow completion steps in between.

```
Source Code
    ↓
┌──────────────────────┐
│ Pass 1: PreProcessor │  (Discovers definitions, builds scope tree)
└──────────┬───────────┘
           ↓
    complete_definitions() (Initial data-flow propagation)
           ↓
┌───────────────────────┐
│ Pass 2: PostProcessor │  (Performs fixed-point assignment analysis)
└──────────┬────────────┘
           ↓
    complete_definitions() (Final data-flow propagation)
           ↓
┌──────────────────────────┐
│ Pass 3: CallGraphProcessor│  (Constructs call graph using closure)
└──────────┬─────────────────┘
           ↓
      Final Call Graph
```

## Module Breakdown

### `cppcg/processing` - The Analysis Pipeline

This module contains the core logic for each pass of the analysis.

*   **`preprocessor.py` (Pass 1)**: This pass walks the syntax tree to discover all top-level definitions and build an initial scope tree. It identifies all functions, structs, unions, enums, typedefs, and global variables and creates `Definition` objects for them.

*   **`postprocessor.py` (Pass 2)**: This pass performs the main data-flow analysis. It runs in a fixed-point loop (driven by `complete_definitions`) to model all assignments and build a complete *assignment graph*.

*   **`cgprocessor.py` (Pass 3)**: This is the final pass that constructs the call graph. It walks the AST, and for each `call_expression`, it uses the completed assignment graph and a pre-computed transitive closure to resolve all possible direct, indirect (function pointers), and external calls.

### `cppcg/machinery` - Core Data Structures

This module defines the fundamental data structures used to represent the code and the analysis state.

*   **`definitions.py`**: Defines the `Definition` class, which represents any named entity in the code (e.g., a variable, function, or type), and the `DefinitionManager`, which manages the collection of all definitions. The manager provides two critical operations:
    *   `complete_definitions()`: The core engine for inter-procedural data-flow analysis. It iteratively propagates argument values from call sites to the parameters of all possible target functions, running in a fixed-point loop until the assignment graph stabilizes.
    *   `transitive_closure()`: A utility function used to efficiently query the fully constructed assignment graph. It pre-calculates, for every definition, the complete set of all other definitions it could potentially point to, whether directly or through a chain of pointers.

*   **`scopes.py`**: Implements the `Scope` class and the `ScopeManager`, which maintains the program's scope tree and the definitions visible within each scope.

*   **`pointers.py`**: Defines `NamePointer` and `LiteralPointer` classes. These are attached to `Definition` objects to represent the set of other definitions or literal values that a variable can point to. They form the edges of the assignment graph.

*   **`callgraph.py`**: Provides data structures for storing and manipulating the final call graph.

*   **`files.py`**: A utility module for managing and resolving file paths.

### `cppcg/formats` - Output Serialization

This module is responsible for converting the generated call graph into various output formats, such as simple JSON.

### `cppcg/utils` - Utilities

Contains common helper functions, constants, and data structures used across the project.

## Implementation Details

### Transitive Closure Resolution
The `CallGraphProcessor` uses the `transitive_closure()` result to resolve indirect calls. The process is as follows:
1. For a call like `p->func(...)`, it first resolves all possible definitions for the variable `p`.
2. For each definition of `p`, it looks up the `.func` field.
3. For each field, it uses the pre-computed closure to find all reachable function definitions.
4. All reachable functions become potential targets in the final call graph.

### External Function Handling
External functions (e.g., `malloc`, `printf`) are detected by name. They are created as special `Definition` objects with a `DefType.EXT_DEF` flag, allowing them to be clearly marked as external dependencies in the final call graph.

## Future Enhancements
Potential improvements for the project include:
1. Context-sensitive analysis for more precise call graphs.
2. Inter-procedural constant propagation.
3. Support for function pointers stored in arrays.
4. Call graph visualization tools.
5. Generation of call graph metrics (e.g., depth, complexity).