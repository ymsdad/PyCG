#!/usr/bin/env python3
"""
End-to-end test for CppCG call graph generation.
This script demonstrates how to use CppCG programmatically.
"""

import sys
from pathlib import Path

# Add cppcg parent directory to path so we can import cppcg as a package
sys.path.insert(0, str(Path(__file__).parent))

# Now import from the cppcg package - but imports within cppcg are absolute
# For demonstration, we'll use the test approach
sys.path.insert(0, str(Path(__file__).parent / "cppcg"))

from machinery.callgraph import CallGraph
from machinery.definitions import DefinitionManager
from machinery.scopes import ScopeManager
from machinery.files import FileManager
from machinery.funcs import FuncManager
from processing.preprocessor import PreProcessor
from processing.postprocessor import PostProcessor
from processing.cgprocessor import CallGraphProcessor
import json

# Test with the example C file
code_file = Path(__file__).parent / "test_example.c"

if not code_file.exists():
    print(f"Error: {code_file} not found")
    sys.exit(1)

print(f"Analyzing {code_file}...")

# Read the code
with open(code_file, "r") as f:
    code = f.read()

# Initialize managers
def_manager = DefinitionManager()
scope_manager = ScopeManager()
file_manager = FileManager(".")
func_manager = FuncManager()
cg = CallGraph()

# Run all three passes
pre = PreProcessor(def_manager, file_manager, func_manager, scope_manager)
pre.analyze_code(code)
def_manager.complete_definitions()

post = PostProcessor(def_manager, file_manager, func_manager, scope_manager)
post.analyze_code(code)
def_manager.complete_definitions()

cgproc = CallGraphProcessor(def_manager, file_manager, func_manager, scope_manager, cg)
cgproc.analyze_code(code)

# Get results
call_graph = cg.get()
edges = cg.get_edges()
functions = [ns for ns, defi in def_manager.get_defs().items() if defi.is_function_def()]

print(f"\n=== Call Graph ===")
print(f"Functions found: {len(functions)}")
for func in sorted(functions):
    print(f"  - {func}")

print(f"\nCall Graph Edges: {len(edges)}")
for src, dst in sorted(edges):
    print(f"  {src} -> {dst}")

# Validate expected edges
expected_edges = [
    ("<global>.main", "<global>.init"),
    ("<global>.main", "<global>.printf"),
    ("<global>.init", "<global>.malloc"),
]

print(f"\n=== Validation ===")
for src, dst in expected_edges:
    if [src, dst] in edges:
        print(f"✓ {src} -> {dst}")
    else:
        print(f"✗ {src} -> {dst} (MISSING)")

# Check for indirect call resolution
has_main_to_add = any(
    src == "<global>.main" and dst == "<global>.add"
    for src, dst in edges
)
if has_main_to_add:
    print(f"✓ <global>.main -> <global>.add (indirect)")
else:
    print(f"✗ <global>.main -> <global>.add (indirect) - may require deeper analysis")

print(f"\n=== Summary ===")
print(f"Analysis completed successfully!")
print(f"Total call graph nodes: {len(call_graph)}")
print(f"Total call graph edges: {len(edges)}")

# Save to JSON
output_file = Path(__file__).parent / "test_example_cg.json"
with open(output_file, "w") as f:
    json.dump(call_graph, f, indent=2, default=lambda x: list(x) if isinstance(x, set) else str(x))

print(f"Call graph saved to: {output_file}")
