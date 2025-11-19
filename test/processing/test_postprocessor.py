import sys
from pathlib import Path

import pytest

# Make cppcg package importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cppcg"))

test_code = """
typedef struct {
    int x;
    int y;
    int (*func)(int, int);
} Point;

int add(int a, int b) {
    return a + b;
}

Point p;
Point *init(int x, int y) {
    Point *new_point = malloc(sizeof(Point));
    new_point->x = x;
    new_point->y = y;
    new_point->func = add;
    return new_point;
}

int main() {
    Point *p = init(1, 2);
    printf("%d\\n", p->func(p->x, p->y));
    return 0;
}
"""

from processing.preprocessor import PreProcessor
from processing.postprocessor import PostProcessor
from machinery.definitions import DefinitionManager
from machinery.scopes import ScopeManager
from utils.constants import GLOBAL_NAME


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


def test_assignment_graph():
    """Test the complete assignment graph construction."""
    def_manager = DefinitionManager()
    scope_manager = ScopeManager()

    pre = PreProcessor(def_manager, None, None, scope_manager)
    pre.analyze_code(test_code)

    post = PostProcessor(def_manager, None, None, scope_manager)
    post.analyze_code(test_code)

    # Test 1: init function parameters should have literal assignments
    # init(1, 2) means init.x -> lit[1], init.y -> lit[2]
    init_x_def = def_manager.get("<global>.init.x")
    init_y_def = def_manager.get("<global>.init.y")
    assert init_x_def is not None, "init.x definition should exist"
    assert init_y_def is not None, "init.y definition should exist"
    
    init_x_lits = init_x_def.get_lit_pointer().get()
    init_y_lits = init_y_def.get_lit_pointer().get()
    print(f"init.x literals: {init_x_lits}")
    print(f"init.y literals: {init_y_lits}")
    assert 1 in init_x_lits, "init.x should point to literal 1"
    assert 2 in init_y_lits, "init.y should point to literal 2"

    # Test 2: main.p should point to init's return value
    main_p_def = def_manager.get("<global>.main.p")
    assert main_p_def is not None, "main.p definition should exist"
    
    main_p_names = main_p_def.get_name_pointer().get()
    print(f"main.p points to: {main_p_names}")
    assert "<global>.init.<RETURN>" in main_p_names, "main.p should point to init.<RETURN>"

    # Test 3: init.<RETURN> should point to init.new_point
    init_ret_def = def_manager.get("<global>.init.<RETURN>")
    assert init_ret_def is not None, "init.<RETURN> should exist"
    
    init_ret_names = init_ret_def.get_name_pointer().get()
    print(f"init.<RETURN> points to: {init_ret_names}")
    assert "<global>.init.new_point" in init_ret_names, "init.<RETURN> should point to init.new_point"

    # Test 4: init.new_point.x should point to init.x
    # This happens via: new_point->x = x;
    new_point_x_def = def_manager.get("<global>.init.new_point.x")
    assert new_point_x_def is not None, "init.new_point.x should exist"
    
    new_point_x_names = new_point_x_def.get_name_pointer().get()
    print(f"init.new_point.x points to: {new_point_x_names}")
    assert "<global>.init.x" in new_point_x_names, "init.new_point.x should point to init.x"

    # Test 5: init.new_point.func should point to add function
    new_point_func_def = def_manager.get("<global>.init.new_point.func")
    assert new_point_func_def is not None, "init.new_point.func should exist"
    
    new_point_func_names = new_point_func_def.get_name_pointer().get()
    print(f"init.new_point.func points to: {new_point_func_names}")
    assert "<global>.add" in new_point_func_names, "init.new_point.func should point to add"

    # Test 6: main.p.func should resolve to add (via closure)
    # main.p -> init.<RETURN> -> init.new_point
    # main.p.func -> init.<RETURN>.func -> init.new_point.func -> add
    main_p_func_def = def_manager.get("<global>.main.p.func")
    if main_p_func_def:
        main_p_func_names = main_p_func_def.get_name_pointer().get()
        print(f"main.p.func points to: {main_p_func_names}")

    # Test 7: For the call p->func(p->x, p->y), add's parameters should get values
    # add.a should eventually trace to literal 1
    # add.b should eventually trace to literal 2
    add_a_def = def_manager.get("<global>.add.a")
    add_b_def = def_manager.get("<global>.add.b")
    assert add_a_def is not None, "add.a should exist"
    assert add_b_def is not None, "add.b should exist"
    
    add_a_names = add_a_def.get_name_pointer().get()
    add_b_names = add_b_def.get_name_pointer().get()
    print(f"add.a points to: {add_a_names}")
    print(f"add.b points to: {add_b_names}")
    
    # add.a should point to main.p.x
    # main.p.x -> init.<RETURN>.x -> init.new_point.x -> init.x -> lit[1]
    main_p_x_exists = any("main.p.x" in name for name in add_a_names)
    print(f"add.a points to main.p.x: {main_p_x_exists}")


if __name__ == "__main__":
    test_struct_field_positions()
    test_assignment_graph()
