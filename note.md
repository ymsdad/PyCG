# Field Declaration Processing - FIXED ✓

## Preprocessor (`cppcg/processing/preprocessor.py`):
**Fixed:** `visit_field_declaration` now uses the visitor pattern correctly:
- `visit_struct_specifier` creates the struct def, pushes struct name to stack, then calls `self.visit(body_node)` to visit children normally
- `visit_field_declaration` is invoked by the visitor pattern for each field
- Uses `self.current_ns` to get the parent struct scope and definition
- Creates field definitions and registers them as positional arguments in the parent struct's `NamePointer`
- Field positions tracked correctly (0, 1, 2, ...)

Removed: `__handle_field_declaration` (no longer needed)

## Postprocessor (`cppcg/processing/postprocessor.py`):
**Working correctly:** `visit_field_expression`:
- Creates instance field definitions
- Links to struct field definitions  
- Follows parent's name pointer chain to find all reachable instance fields
- Properly resolves chains like `main.p -> init.<RETURN> -> init.new_point`

**Fixed:** `visit_call_expression`:
- Moved argument evaluation BEFORE checking if func_defs is empty
- Ensures nested calls are visited even when outer call target is unresolved (e.g., `printf`)

## Test Results
All tests passing ✓
- `test_struct_field_positions`: Validates struct fields registered as positional arguments
- `test_assignment_graph`: Validates complete assignment graph construction including function calls and struct field access
