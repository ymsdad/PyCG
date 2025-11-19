from tree_sitter import Node as TSNode
from typing import Optional, List, Tuple, Union, Any

import utils
from machinery.definitions import Definition
from utils.constants import DefType, RETURN_NAME

from .base import ProcessingBase

IDefinition = Union[int, str, Definition]

class PostProcessor(ProcessingBase):
    def __init__(
        self, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)

    # modified visitor for expression
    def visit(self, node: TSNode) -> Any:
        method = "visit_" + node.type
        visitor = getattr(self, method, None)
        if visitor:
            return visitor(node)
        if node.type.endswith("_expression"):
            return self.visit_expression(node)
        return self.generic_visit(node)

    def visit_expression(self, node: TSNode) -> List[IDefinition]:
        if node is None:
            return []
        t = node.type
        if t == "identifier":
            id_name = node.text.decode("utf-8").strip()
            defi = self.scope_manager.get_def(self.current_ns, id_name)
            if not defi:
                defi, _ = self._create_def_and_scope(id_name, DefType.NAME_DEF)
            return [defi]
        elif t == "number_literal":
            return [int(node.text.decode("utf-8").strip())]
        elif t in (            
            "true",
            "false",
            "null",
        ):
            return [node.text.decode("utf-8").strip()]
        elif t in (
            "string_literal",
            "char_literal",
        ):
            return [node.children[1].text.decode("utf-8").strip()]
        elif t == "concatenated_string":
            results = []
            for child in node.children:
                if child.type in ("identifier", "string_literal"):
                    results.extend(self.visit_expression(child))
            return results
        visitor = getattr(self, "visit_" + t, None)
        if visitor:
            return visitor(node)
        return []

    def _assign_from_values(self, left_def: Definition, right_vals: List[IDefinition]):
        """Wire values in right_vals into left_def's pointers.

        This centralizes assignment semantics so it can be reused from
        regular assignments, initializers, returns, and parameter binding.
        It also handles the special case of struct variables initialized
        from an initializer_list result.
        """
        lit_ptr = left_def.get_lit_pointer()
        name_ptr = left_def.get_name_pointer()

        for rv in right_vals:
            if isinstance(rv, Definition):
                name_ptr.add(rv.get_ns())
            elif isinstance(rv, (int, str)):
                lit_ptr.add(rv)

        # Special-case: struct-like object initialized from an initializer_list
        self._assign_struct_fields_from_initializers(left_def, right_vals)

    def _resolve_struct_type(self, var_def: Definition) -> Optional[Definition]:
        """Try to resolve the struct/union type definition of a variable.

        We follow the variable's type names (stored in its NamePointer values)
        and any typedef indirections, and return the first TYPE_DEF whose
        scope contains NAME_DEF fields (as produced by PreProcessor's
        visit_field_declaration).
        """
        name_ptr = var_def.get_name_pointer()
        to_visit = list(name_ptr.get())
        visited: set[str] = set()

        while to_visit:
            name = to_visit.pop()
            if name in visited:
                continue
            visited.add(name)

            # Look up a type definition for this name in the visible scopes
            # or in the global definition manager as a fallback.
            type_def = self.scope_manager.get_def(self.current_ns, name)
            if not type_def:
                type_def = self.def_manager.get(name)
            if not type_def:
                continue

            if not (type_def.get_type() & DefType.TYPE_DEF):
                continue

            # A "struct-like" type is any TYPE_DEF whose scope has NAME_DEF
            # entries (its fields), regardless of whether the scope node was
            # stored (typedefs typically have no node saved).
            type_scope = self.scope_manager.get_scope(type_def.get_ns())
            if type_scope:
                defs = type_scope.get_defs()
                if any(d.get_type() & DefType.NAME_DEF for d in defs.values()):
                    return type_def

            # Otherwise follow typedef chains via the type's own name pointer.
            for next_name in type_def.get_name_pointer().get():
                if next_name not in visited:
                    to_visit.append(next_name)

        return None

    def _assign_struct_fields_from_initializers(
        self, left_def: Definition, right_vals: List[IDefinition]
    ):
        """If left_def is a struct-like object and right_vals contain
        initializer_list result definitions, map initializer elements to
        per-field definitions under left_def's namespace.
        """
        struct_def = self._resolve_struct_type(left_def)
        if not struct_def:
            return

        struct_scope = self.scope_manager.get_scope(struct_def.get_ns())
        if not struct_scope:
            return

        struct_defs = struct_scope.get_defs()
        field_names: List[str] = [
            name
            for name, defi in struct_defs.items()
            if defi.get_type() & DefType.NAME_DEF
        ]
        if not field_names:
            return

        # Collect initializer_list result definitions from RHS.
        init_defs: List[Definition] = []
        for rv in right_vals:
            if isinstance(rv, Definition) and not rv.is_function_def():
                init_np = rv.get_name_pointer()
                if init_np.get_args():
                    init_defs.append(rv)

        if not init_defs:
            return

        for init_def in init_defs:
            init_np = init_def.get_name_pointer()

            for idx, field_name in enumerate(field_names):
                # Create / get the field definition under the instance namespace.
                field_def, _ = self._create_def_and_scope(
                    field_name, DefType.NAME_DEF, parent_ns=left_def.get_ns()
                )

                # Prefer named designators (e.g., .y = ...) over positional ones.
                src = init_np.get_arg(field_name)
                if not src:
                    src = init_np.get_pos_arg(idx)
                if not src:
                    continue

                for item in src:
                    target_def = self.def_manager.get(item)
                    if target_def:
                        field_def.get_name_pointer().add(target_def.get_ns())
                    else:
                        # For literals we only know their kind (STRING/INTEGER/UNKNOWN).
                        field_def.get_lit_pointer().add(item)

    def _resolve_call_targets(self, callee_vals: List[IDefinition]) -> List[Definition]:
        """Compute a closure of possible function targets for a call.

        Starting from direct callee values, recursively traverse name
        pointers to discover all reachable function definitions.
        """
        start_defs: List[Definition] = []
        for v in callee_vals:
            if isinstance(v, Definition):
                start_defs.append(v)
            elif isinstance(v, str):
                d = self.def_manager.get(v)
                if not d:
                    d = self.scope_manager.get_def(self.current_ns, v)
                if d:
                    start_defs.append(d)

        results: List[Definition] = []
        visited = set()
        stack: List[Definition] = list(start_defs)

        while stack:
            d = stack.pop()
            ns = d.get_ns()
            if ns in visited:
                continue
            visited.add(ns)

            if d.is_function_def():
                results.append(d)

            name_ptr = d.get_name_pointer()
            for name in name_ptr.get():
                if name in visited:
                    continue
                target = self.def_manager.get(name)
                if target:
                    stack.append(target)
                else:
                    scope_def = self.scope_manager.get_def(self.current_ns, name)
                    if scope_def:
                        stack.append(scope_def)

        return results

    def visit_call_expression(self, node: TSNode) -> List[IDefinition]:
        results: List[IDefinition] = []
        func_node = node.child_by_field_name("function")
        if not func_node and node.children:
            func_node = node.children[0]
        if not func_node:
            return []

        # Resolve callee definitions
        callee_vals = self.visit_expression(func_node)
        func_defs = self._resolve_call_targets(callee_vals)

        # Evaluate call arguments BEFORE checking if func_defs is empty,
        # so that nested calls are visited even if the outer call target is unknown
        args_node = node.child_by_field_name("arguments")
        arg_vals_list: List[List[IDefinition]] = []
        if args_node:
            for ch in args_node.children:
                if not ch.is_named:
                    continue
                if ch.type == "compound_statement":
                    arg_vals_list.append(self.visit_compound_statement(ch))
                else:
                    arg_vals_list.append(self.visit_expression(ch))

        if not func_defs:
            return []

        for func_def in func_defs:
            func_ns = func_def.get_ns()
            func_scope = self.scope_manager.get_scope(func_ns)
            if not func_scope or not func_scope.node:
                continue

            # Bind arguments to parameters using the function's NamePointer
            func_name_ptr = func_def.get_name_pointer()
            pos_to_name = func_name_ptr.get_pos_names()
            for pos, param_name in pos_to_name.items():
                try:
                    idx = int(pos)
                except (TypeError, ValueError):
                    continue
                if idx < 0 or idx >= len(arg_vals_list):
                    continue
                arg_vals = arg_vals_list[idx]
                param_def = func_scope.get_def(param_name)
                if not param_def:
                    continue
                self._assign_from_values(param_def, arg_vals)

            # Visit the function body in its own namespace
            func_node_def = func_scope.node
            if not func_node_def:
                continue
            body = func_node_def.child_by_field_name("body")
            if body:
                prev_stack = list(self.name_stack)
                self.name_stack = func_ns.split(".")
                self.visit(body)
                self.name_stack = prev_stack

            # Use the function's RETURN_NAME definition as call result
            ret_ns = utils.join_ns(func_ns, RETURN_NAME)
            ret_def = self.def_manager.get(ret_ns)
            if ret_def:
                results.append(ret_def)

        return results

    def visit_assignment_expression(self, node: TSNode) -> List[IDefinition]:
        left_node = node.child_by_field_name("left")
        right_node = node.child_by_field_name("right")
        if not left_node or not right_node:
            return []

        left_vals = self.visit_expression(left_node)
        right_vals = self.visit_expression(right_node)

        left_defs = [v for v in left_vals if isinstance(v, Definition)]
        if not left_defs:
            # If LHS did not resolve to a definition, nothing to wire.
            return left_vals

        for left_def in left_defs:
            self._assign_from_values(left_def, right_vals)

        return left_defs

    def visit_return_statement(self, node: TSNode) -> List[IDefinition] :
        ret_ns = utils.join_ns(self.current_ns, RETURN_NAME)
        ret_def = self.def_manager.get(ret_ns)
        if not ret_def:
            ret_def, _ = self._create_def_and_scope(RETURN_NAME, DefType.NAME_DEF)

        if len(node.children) >= 2:
            vals = self.visit_expression(node.children[1])
            self._assign_from_values(ret_def, vals)

        return [ret_def]

    def visit_init_declarator(self, node: TSNode) -> List[IDefinition]:
        decl_node = node.child_by_field_name("declarator")
        if decl_node:
            decl_name, _ = self._visit_decl_decl(decl_node)
        else:
            field_counter = self.scope_manager.get_scope(self.current_ns).inc_field_counter()
            decl_name = utils.get_field_name(field_counter)

        left_def = self.scope_manager.get_def(self.current_ns, decl_name)
        if not left_def:
            left_def, _ = self._create_def_and_scope(decl_name, DefType.NAME_DEF)

        value_node = node.child_by_field_name("value")
        if not value_node:
            return [left_def]

        if value_node.type == "initializer_list":
            right_vals = self.visit_initializer_list(value_node)
        else:
            right_vals = self.visit_expression(value_node)

        self._assign_from_values(left_def, right_vals)
        return [left_def]

    def visit_compound_statement(self, node: TSNode) -> List[IDefinition]:
        last_results: List[IDefinition] = []
        for child in node.children:
            if not child.is_named:
                continue
            res = self.visit(child)
            if child.type.endswith("_expression") or child.type in ("expression_statement", "return_statement"):
                if not res:
                    last_results = []
                elif isinstance(res, list):
                    last_results = res
                else:
                    last_results = [res]
        return last_results

    def visit_conditional_expression(self, node: TSNode) -> List[IDefinition]:
        results: List[IDefinition] = []
        cond_node = node.child_by_field_name("condition")
        conseq_node = node.child_by_field_name("consequence")
        alt_node = node.child_by_field_name("alternative")
        if cond_node:
            self.visit(cond_node)
        if conseq_node:
            results.extend(self.visit_expression(conseq_node))
        if alt_node:
            results.extend(self.visit_expression(alt_node))
        return results

    def visit_unary_expression(self, node: TSNode) -> List[IDefinition]:
        arg = node.child_by_field_name("argument")
        return self.visit_expression(arg)

    def visit_update_expression(self, node: TSNode) -> List[IDefinition]:
        arg = node.child_by_field_name("argument")
        return self.visit_expression(arg)

    def visit_cast_expression(self, node: TSNode) -> List[IDefinition]:
        type_node = node.child_by_field_name("type")
        value_node = node.child_by_field_name("value")
        self.visit(type_node)
        return self.visit_expression(value_node)

    def visit_pointer_expression(self, node: TSNode) -> List[IDefinition]:
        arg = node.child_by_field_name("argument")
        return self.visit_expression(arg)

    def visit_sizeof_expression(self, node: TSNode) -> List[IDefinition]:
        type_node = node.child_by_field_name("type")
        if type_node:
            self.visit(type_node)
        value_node = node.child_by_field_name("value")
        if value_node:
            self.visit(value_node)
        return [self._get_base_type_def()]

    def visit_alignof_expression(self, node: TSNode) -> List[IDefinition]:
        type_node = node.child_by_field_name("type")
        if type_node:
            self.visit(type_node)
        return [self._get_base_type_def()]

    def visit_offsetof_expression(self, node: TSNode) -> List[IDefinition]:
        type_node = node.child_by_field_name("type")
        if type_node:
            self.visit(type_node)
        member_node = node.child_by_field_name("member")
        if member_node:
            self.visit(member_node)
        return [self._get_base_type_def()]

    def visit_generic_expression(self, node: TSNode) -> List[IDefinition]:
        results = []
        child_len = len(node.children)
        for i in range(2, child_len, step=2):
            if i % 4 ==0:
                self.visit(node.children[i])
            else:
                results.extend(self.visit_expression(node.children[i]))
        return results

    def visit_subscript_expression(self, node: TSNode) -> List[IDefinition]:
        index_node = node.child_by_field_name("index")
        if index_node:
            self.visit(index_node)
        arg = node.child_by_field_name("argument")
        return self.visit_expression(arg)

    def visit_binary_expression(self, node: TSNode) -> List[IDefinition]:
        results = []
        left_defs = self.visit_expression(node.child_by_field_name("left"))
        right_defs = self.visit_expression(node.child_by_field_name("right"))
        results.extend(left_defs)
        results.extend(right_defs)
        return results

    def visit_gnu_asm_expression(self, node: TSNode) -> List[IDefinition]:
        self.generic_visit(node)
        return []

    def visit_comma_expression(self, node: TSNode) -> List[IDefinition]:
        self.visit_expression(node.child_by_field_name("left"))
        return self.visit_expression(node.child_by_field_name("right"))

    def visit_parenthesized_expression(self, node: TSNode) -> List[IDefinition]:
        return self.visit(node.children[1])

    def visit_extension_expression(self, node: TSNode) -> List[IDefinition]:
        return self.visit_expression(node.children[1])

    def visit_compound_literal_expression(self, node: TSNode) -> List[IDefinition]:
        # this case can be complicated, the initialized part can be a struct or an array
        # thus its ambiguous to determine the type of the compound literal
        # we will just return the type of the initialized part
        type_node = node.child_by_field_name("type")
        value_node = node.child_by_field_name("value")
        if type_node:
            self.visit(type_node)

        # 1. Create the result definition via the initializer_list.
        init_def: Optional[Definition] = None
        if value_node and value_node.type == "initializer_list":
            init_vals = self.visit_initializer_list(value_node)
        elif value_node:
            init_vals = self.visit_expression(value_node)
        else:
            init_vals = []

        for v in init_vals:
            if isinstance(v, Definition):
                init_def = v
                break

        if not init_def:
            # If we couldn't construct an initializer Definition, fall back
            # to whatever the value expression produced.
            return init_vals

        # 2. Resolve the type name in scope and add a pointer to the type, if it exists.
        if type_node:
            inner_type = type_node.child_by_field_name("type") or type_node

            type_name: Optional[str] = None
            if inner_type.type in ("type_identifier", "primitive_type"):
                type_name = inner_type.text.decode("utf-8").strip()
            elif inner_type.type in ("struct_specifier", "union_specifier", "enum_specifier"):
                name_node = inner_type.child_by_field_name("name")
                if name_node:
                    type_name = name_node.text.decode("utf-8").strip()
            else:
                type_name = inner_type.text.decode("utf-8").strip()

            if type_name:
                type_def = self.scope_manager.get_def(self.current_ns, type_name)
                if type_def:
                    init_def.get_name_pointer().add(type_def.get_ns())

        return [init_def]

    def visit_field_expression(self, node: TSNode) -> List[IDefinition]:
        """Handle field access (both . and ->).
        
        For each parent definition, create a field definition and link it
        to the struct's corresponding field AND to all reachable instance fields.
        """
        arg_node = node.child_by_field_name("argument")
        field_node = node.child_by_field_name("field")
        if not arg_node or not field_node:
            return []
        parent_defis = self.visit_expression(arg_node)
        field_name = field_node.text.decode("utf-8").strip()

        results: List[IDefinition] = []
        for parent in parent_defis:
            if not isinstance(parent, Definition):
                continue
            
            # Create the instance field definition
            field_def, _ = self._create_def_and_scope(
                field_name, DefType.NAME_DEF, parent_ns=parent.get_ns()
            )
            results.append(field_def)
            
            # Try to resolve the parent's struct type and link to struct field
            struct_def = self._resolve_struct_type(parent)
            if struct_def:
                struct_scope = self.scope_manager.get_scope(struct_def.get_ns())
                if struct_scope:
                    struct_field_def = struct_scope.get_def(field_name)
                    if struct_field_def:
                        # Link instance field to struct field
                        field_def.get_name_pointer().add(struct_field_def.get_ns())
                        # Copy struct field's type/function pointers to instance field
                        for ptr_name in struct_field_def.get_name_pointer().get():
                            field_def.get_name_pointer().add(ptr_name)
            
            # Also follow the parent's name pointers to find actual instance fields
            # E.g., if parent points to init.<RETURN> which points to init.new_point,
            # then link to init.new_point.field_name
            visited = set()
            to_visit = list(parent.get_name_pointer().get())
            while to_visit:
                target_ns = to_visit.pop()
                if target_ns in visited:
                    continue
                visited.add(target_ns)
                
                target_def = self.def_manager.get(target_ns)
                if not target_def:
                    continue
                
                # Check if this target has a field with the same name
                target_field_ns = utils.join_ns(target_ns, field_name)
                target_field_def = self.def_manager.get(target_field_ns)
                if target_field_def:
                    # Link to this field
                    field_def.get_name_pointer().add(target_field_ns)
                    # Copy its pointers too
                    for ptr_name in target_field_def.get_name_pointer().get():
                        field_def.get_name_pointer().add(ptr_name)
                
                # Continue following the chain
                for next_ns in target_def.get_name_pointer().get():
                    if next_ns not in visited:
                        to_visit.append(next_ns)
        
        return results

    def visit_initializer_list(self, node: TSNode) -> List[IDefinition]:
        # create a initializer_counter defi to hold the initializer list
        # according to the doc, the child can be a initializer_pair/initializer list or an expression/
        # if it's initializer list, then visit self function again, and set pos arg for the def
        # if it's initializer pair, then visit the designator and add_name_arg
        # else visit expression, and add pos arg
        # the result is a list contain a single  defi created by a initializer_counter
        current_sc = self.scope_manager.get_scope(self.current_ns)
        if not current_sc:
            return []

        init_idx = current_sc.inc_initializer_counter()
        init_name = utils.get_initializer_name(init_idx)

        init_def, _ = self._create_def_and_scope(init_name, DefType.NAME_DEF)
        name_ptr = init_def.get_name_pointer()

        pos = 0
        for child in node.children:
            if not child.is_named:
                continue

            if child.type == "initializer_pair":
                designator_node = child.child_by_field_name("designator")
                value_node = child.child_by_field_name("value")
                if not designator_node or not value_node:
                    self.visit(child)
                    pos += 1
                    continue

                # Derive a designator name (field or index); fall back to raw text.
                designator_name = None
                if designator_node.type == "field_designator":
                    fld = designator_node.children[1]
                    if fld:
                        designator_name = fld.text.decode("utf-8").strip()
                if not designator_name:
                    designator_name = designator_node.text.decode("utf-8").strip()

                if value_node.type == "initializer_list":
                    vals = self.visit_initializer_list(value_node)
                else:
                    vals = self.visit_expression(value_node)

                for v in vals:
                    if isinstance(v, Definition):
                        name_ptr.add_name_arg(designator_name, v.get_ns())
                    elif isinstance(v, (int, str)):
                        name_ptr.add_lit_arg(designator_name, v)

            elif child.type == "initializer_list":
                vals = self.visit_initializer_list(child)
                for v in vals:
                    if isinstance(v, Definition):
                        name_ptr.add_pos_arg(pos, None, v.get_ns())
                    elif isinstance(v, (int, str)):
                        name_ptr.add_pos_lit_arg(pos, None, v)
                pos += 1

            else:
                vals = self.visit_expression(child)
                for v in vals:
                    if isinstance(v, Definition):
                        name_ptr.add_pos_arg(pos, None, v.get_ns())
                    elif isinstance(v, (int, str)):
                        name_ptr.add_pos_lit_arg(pos, None, v)
                pos += 1

        return [init_def]
