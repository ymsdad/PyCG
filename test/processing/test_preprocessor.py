import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cppcg"))

TEST_FILE = Path(__file__).resolve().parents[2] / "benchmarks/micro-benchmark/test_example.c"
test_code = TEST_FILE.read_text()
from processing.preprocessor import PreProcessor
from machinery.definitions import DefinitionManager
from machinery.scopes import ScopeManager
from utils.constants import GLOBAL_NAME, RETURN_NAME, DefType


def test_struct_field_positions():
    """Test that struct fields are registered as positional arguments."""
    def_manager = DefinitionManager()
    scope_manager = ScopeManager()

    pre = PreProcessor(def_manager, None, None, scope_manager)
    pre.analyze_code(test_code)

    # Get the Point typedef and its underlying struct
    point_def = scope_manager.get_def(GLOBAL_NAME, "Point")
    assert point_def is not None

    # Follow typedef to struct
    type_names = list(point_def.get_name_pointer().get())
    assert type_names
    struct_name = type_names[0]

    struct_def = scope_manager.get_def(GLOBAL_NAME, struct_name)
    assert struct_def is not None

    # Check that struct has positional field mappings
    struct_name_ptr = struct_def.get_name_pointer()
    pos_to_name = struct_name_ptr.get_pos_names()
    
    print(f"Struct {struct_name} positional fields: {pos_to_name}")
    assert 0 in pos_to_name, "Field x should be at position 0"
    assert 1 in pos_to_name, "Field y should be at position 1"
    assert 2 in pos_to_name, "Field func should be at position 2"
    assert pos_to_name[0] == "x"
    assert pos_to_name[1] == "y"
    assert pos_to_name[2] == "func"

def test_preprocessor_scope():
    def_manager = DefinitionManager()
    scope_manager = ScopeManager()
    preprocessor = PreProcessor(def_manager, None, None, scope_manager)
    preprocessor.analyze_code(test_code)

    # Global scope should exist
    global_scope = scope_manager.get_scope(GLOBAL_NAME)
    assert global_scope is not None

    # Typedef Point and its underlying struct
    point_def = scope_manager.get_def(GLOBAL_NAME, "Point")
    assert point_def is not None

    type_names = list(point_def.get_name_pointer().get())
    assert type_names, "Point typedef should point to underlying struct type"
    struct_name = type_names[0]

    struct_def = scope_manager.get_def(GLOBAL_NAME, struct_name)
    assert struct_def is not None

    struct_scope = scope_manager.get_scope(struct_def.get_ns())
    assert struct_scope is not None

    # Struct fields x, y, func
    struct_field_names = set(struct_scope.get_defs().keys())
    assert {"x", "y", "func"}.issubset(struct_field_names)

    # Struct NamePointer should have positional fields 0:x, 1:y, 2:func
    struct_name_ptr = struct_def.get_name_pointer()
    pos_to_name = struct_name_ptr.get_pos_names()
    assert pos_to_name.get(0) == "x"
    assert pos_to_name.get(1) == "y"
    assert pos_to_name.get(2) == "func"

    # Global variable p
    global_p_def = scope_manager.get_def(GLOBAL_NAME, "p")
    assert global_p_def is not None
    assert global_p_def.get_type() & DefType.NAME_DEF

    # Function add and its parameters a, b, return
    add_def = scope_manager.get_def(GLOBAL_NAME, "add")
    assert add_def is not None and add_def.is_function_def()

    add_scope = scope_manager.get_scope(add_def.get_ns())
    assert add_scope is not None
    add_locals = set(add_scope.get_defs().keys())
    assert {"a", "b", RETURN_NAME}.issubset(add_locals)

    # Function init and its parameters x, y, return
    init_def = scope_manager.get_def(GLOBAL_NAME, "init")
    assert init_def is not None and init_def.is_function_def()

    init_scope = scope_manager.get_scope(init_def.get_ns())
    assert init_scope is not None
    init_locals = set(init_scope.get_defs().keys())
    assert {"x", "y", RETURN_NAME}.issubset(init_locals)

    # Argument scopes for init.x and init.y should exist
    init_x_ns = f"{init_def.get_ns()}.x"
    init_y_ns = f"{init_def.get_ns()}.y"
    assert def_manager.get(init_x_ns) is not None
    assert def_manager.get(init_y_ns) is not None
    assert scope_manager.get_scope(init_x_ns) is not None
    assert scope_manager.get_scope(init_y_ns) is not None

    # Basic sanity: function main definition exists
    main_def = scope_manager.get_def(GLOBAL_NAME, "main")
    assert main_def is not None and main_def.is_function_def()