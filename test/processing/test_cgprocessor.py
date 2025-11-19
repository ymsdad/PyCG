import sys
from pathlib import Path

# Make cppcg package importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cppcg"))

from processing.preprocessor import PreProcessor
from processing.postprocessor import PostProcessor
from processing.cgprocessor import CallGraphProcessor
from machinery.definitions import DefinitionManager
from machinery.scopes import ScopeManager
from machinery.files import FileManager
from machinery.funcs import FuncManager
from machinery.callgraph import CallGraph
from utils.constants import GLOBAL_NAME

TEST_FILE = Path(__file__).resolve().parents[2] / "benchmarks/micro-benchmark/test_example.c"
test_code = TEST_FILE.read_text()


def test_call_graph_construction():
    """Test that cgprocessor correctly constructs the call graph."""
    def_manager = DefinitionManager()
    scope_manager = ScopeManager()
    file_manager = FileManager(".")
    func_manager = FuncManager()
    cg = CallGraph()

    # Run all three passes
    pre = PreProcessor(def_manager, file_manager, func_manager, scope_manager)
    pre.analyze_code(test_code)
    
    def_manager.complete_definitions()

    post = PostProcessor(def_manager, file_manager, func_manager, scope_manager)
    post.analyze_code(test_code)
    
    def_manager.complete_definitions()

    cgproc = CallGraphProcessor(def_manager, file_manager, func_manager, scope_manager, cg)
    cgproc.analyze_code(test_code)

    # Get the call graph
    call_graph = cg.get()
    edges = cg.get_edges()

    print(f"\\nCall Graph Nodes: {list(call_graph.keys())}")
    print(f"Call Graph Edges:")
    for src, dst in edges:
        print(f"  {src} -> {dst}")

    # Test main -> init
    main_ns = f"{GLOBAL_NAME}.main"
    init_ns = f"{GLOBAL_NAME}.init"
    add_ns = f"{GLOBAL_NAME}.add"
    malloc_ns = f"{GLOBAL_NAME}.malloc"
    printf_ns = f"{GLOBAL_NAME}.printf"

    assert main_ns in call_graph, "main should be in call graph"
    assert init_ns in call_graph[main_ns], f"main should call init, got: {call_graph.get(main_ns, set())}"

    # Test main -> add (via p->func call)
    # This should be resolved through the assignment graph
    assert add_ns in call_graph.get(main_ns, set()) or any(
        add_ns in call_graph.get(target, set()) 
        for target in call_graph.get(main_ns, set())
    ), f"main (or its callees) should eventually call add"

    # Test init -> malloc (external function)
    assert init_ns in call_graph, "init should be in call graph"
    assert malloc_ns in call_graph[init_ns], f"init should call malloc, got: {call_graph.get(init_ns, set())}"

    # Check that malloc is marked as external
    malloc_def = def_manager.get(malloc_ns)
    assert malloc_def is not None, "malloc definition should exist"
    assert malloc_def.is_ext_def(), "malloc should be marked as external"

    # Test main -> printf
    assert printf_ns in call_graph[main_ns], f"main should call printf, got: {call_graph.get(main_ns, set())}"

    # Check that printf is marked as external
    printf_def = def_manager.get(printf_ns)
    assert printf_def is not None, "printf definition should exist"
    assert printf_def.is_ext_def(), "printf should be marked as external"


def test_indirect_call_resolution():
    """Test that indirect calls through function pointers are resolved."""
    def_manager = DefinitionManager()
    scope_manager = ScopeManager()
    file_manager = FileManager(".")
    func_manager = FuncManager()
    cg = CallGraph()

    # Run all three passes
    pre = PreProcessor(def_manager, file_manager, func_manager, scope_manager)
    pre.analyze_code(test_code)
    
    def_manager.complete_definitions()

    post = PostProcessor(def_manager, file_manager, func_manager, scope_manager)
    post.analyze_code(test_code)
    
    def_manager.complete_definitions()

    cgproc = CallGraphProcessor(def_manager, file_manager, func_manager, scope_manager, cg)
    cgproc.analyze_code(test_code)

    # Get the call graph
    call_graph = cg.get()
    edges = cg.get_edges()

    main_ns = f"{GLOBAL_NAME}.main"
    add_ns = f"{GLOBAL_NAME}.add"

    # The call p->func(p->x, p->y) in main should resolve to add
    # Check if main has a path to add
    def has_path(start, end, graph, visited=None):
        if visited is None:
            visited = set()
        if start == end:
            return True
        if start in visited:
            return False
        visited.add(start)
        for neighbor in graph.get(start, set()):
            if has_path(neighbor, end, graph, visited):
                return True
        return False

    assert has_path(main_ns, add_ns, call_graph), "main should have a path to add through indirect call"