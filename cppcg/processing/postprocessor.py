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

    def visit_call_expression(self, node: TSNode) -> IDefinition:
        func_node = node.child_by_field_name("function")
        if not func_node and node.children:
            func_node = node.children[0]
        if not func_node:
            return node.text.decode("utf-8").strip()

        callee = self.visit_expression(func_node)

        target_def: Optional[Definition] = None
        if isinstance(callee, Definition):
            target_def = callee
        elif isinstance(callee, str):
            target_def = self.scope_manager.get_def(self.current_ns, callee)

        if target_def:
            ret_ns = utils.join_ns(target_def.get_ns(), RETURN_NAME)
            ret_def = self.def_manager.get(ret_ns)
            if ret_def:
                return ret_def
            return target_def

        # Fallback: create or reuse an anonymous call result definition so
        # callers like __resolve_asignee_ns can always safely use .get_ns().
        anon_ns = f"{self.current_ns}.<call>"
        defi = self.def_manager.get(anon_ns)
        if not defi:
            defi = self.def_manager.create(anon_ns, DefType.UNKNOWN)
        return defi

    def visit_assignment_expression(self, node: TSNode) -> IDefinition:
        left_node = node.child_by_field_name("left")
        right_node = node.child_by_field_name("right")
        if not left_node or not right_node:
            return f"{self.current_ns}.<anon>"

        leftns = self.__resolve_asignee_ns(left_node)
        right = self.visit_expression(right_node)
        self.__handle_assign(leftns, right)

        results: List[IDefinition] = []
        defi = self.def_manager.get(leftns)
        if defi:
            return defi
        return leftns

    def visit_return_statement(self, node: TSNode):
        leftns = utils.join_ns(self.current_ns, RETURN_NAME)

    def visit_init_declarator(self, node: TSNode):
        decl_node = node.child_by_field_name("declarator")
        if decl_node:
            decl_name, _= self._visit_decl_decl(decl_node)
        else:
            field_counter = self.scope_manager.get_scope(self.current_ns).inc_field_counter()
            decl_name = utils.get_field_name(field_counter)
        leftns = utils.join_ns(self.current_ns, decl_name)


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
        pass

    def visit_field_expression(self, node: TSNode) -> List[IDefinition]:
        # first visit the parent part (argument child ) to get the parent defis
        # then concat the parent defis to the field name to a new ns, create the relevant defi and scope
        # push the current name into stack , then visit child(field) is a better choice
        pass

    def __resolve_asignee_ns(self, node: TSNode) -> str:
        if node.type == "identifier":
            id_name = node.text.decode("utf-8").strip()
            defi = self.scope_manager.get_def(self.current_ns, id_name)
            if not defi:
                defi, _ = self._create_def_and_scope(id_name, DefType.NAME_DEF)
            return defi.get_ns()
        elif node.type == "field_expression":
            parent_ns = self.__resolve_asignee_ns(node.child_by_field_name("argument"))
            field_name = node.child_by_field_name("field").text.decode("utf-8").strip()
            _, field_defi = self._create_def_and_scope(
                field_name, DefType.NAME_DEF, parent_ns=parent_ns)
            return field_defi.get_ns()
        elif node.type == "pointer_expression":
            return self.__resolve_asignee_ns(node.child_by_field_name("argument"))
        elif node.type == "subscript_expression":
            return self.__resolve_asignee_ns(node.child_by_field_name("argument"))
        elif node.type == "parenthesized_expression":
            return self.__resolve_asignee_ns(node.children[1])
        elif node.type == "call_expression":
            results = self.visit_call_expression(node)
            for res in results:
                if isinstance(res, Definition):
                    return res.get_ns()
            return f"{self.current_ns}.<anon>"
        return f"{self.current_ns}.<anon>"

    def __handle_assign(self, leftns: str, right: IDefinition | List[IDefinition]):
        defi = self.def_manager.get(leftns)
        if not defi:
            defi, _ = self._create_def_and_scope(leftns, DefType.NAME_DEF)

        values: List[IDefinition]
        if isinstance(right, list):
            values = right
        else:
            values = [right]

        for val in values:
            if isinstance(val, str):
                defi.get_lit_pointer().add(val)
            elif isinstance(val, Definition):
                defi.get_name_pointer().add(val.get_ns())