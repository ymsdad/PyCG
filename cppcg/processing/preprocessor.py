
from machinery.definitions import Definition
import utils

from utils.constants import GLOBAL_NAME, RETURN_NAME, DefType, UNKNOWN_RET_TYPE
from .base import ProcessingBase
from typing import List, Tuple
from tree_sitter import Node as TSNode

class PreProcessor(ProcessingBase):
    def __init__(
        self, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)

    def visit_translation_unit(self, node: TSNode):
        defi = self.def_manager.get(GLOBAL_NAME)
        if not defi:
            defi = self.def_manager.create(GLOBAL_NAME, DefType.ROOT_DEF)
        root_sc = self.scope_manager.create_scope(GLOBAL_NAME, None, node)
        root_sc.add_def(GLOBAL_NAME, defi)
        super().visit_translation_unit(node)

    def visit_function_definition(self, node: TSNode):
        func_name, _ = self._visit_decl_decl(node.child_by_field_name("declarator"))
        ret_type = self.__visit_decl_type(node.child_by_field_name("type"))
        self.__handle_function_def(node, func_name, ret_type)
        super().visit_function_definition(node)

    def visit_type_definition(self, node: TSNode):
        self.__visit_declaration(node)

    def visit_lambda_expression(self, node: TSNode):
        current_sc = self.scope_manager.get_scope(self.current_ns)
        lambda_counter = current_sc.inc_lambda_counter()
        lambda_name = utils.get_lambda_name(lambda_counter)
        lambda_def = self.__handle_function_def(node, lambda_name)
        current_sc.add_def(lambda_name, lambda_def)
        super().visit_lambda_expression(node, lambda_name)

    def visit_declaration(self, node: TSNode):
        self.__visit_declaration(node)

    def visit_struct_specifier(self, node: TSNode) -> str:
        name_node = node.child_by_field_name("name")
        if name_node:
            struct_name = name_node.text.decode("utf-8").strip()
        else: 
            struct_counter = self.scope_manager.get_scope(self.current_ns).inc_struct_counter()
            struct_name = utils.get_struct_name(struct_counter)
        self._create_def_and_scope(struct_name, DefType.TYPE_DEF, node)
        body_node = node.child_by_field_name("body")
        if body_node:
            self.name_stack.append(struct_name)
            self.visit(body_node)
            self.name_stack.pop()

        return struct_name

    def visit_field_declaration(self, node: TSNode):
        self.__visit_declaration(node)

    def visit_enumerator(self, node: TSNode):
        name_node = node.child_by_field_name("name")
        if name_node:
            name = name_node.text.decode("utf-8").strip()
            # Create a definition for the enumerator
            self._create_global_def_and_scope(name, DefType.NAME_DEF, node)

    def visit_primitive_type(self, node: TSNode) -> str:
        type_name = node.text.decode("utf-8").strip()
        type_ns = utils.join_ns(GLOBAL_NAME, type_name)
        defi = self.def_manager.get(type_ns)
        if not defi:
            defi = self.def_manager.create(type_ns, DefType.TYPE_DEF)
        self.scope_manager.get_scope(GLOBAL_NAME).add_def(type_name, defi)
        return type_name

    def __visit_declaration(self, node: TSNode):
        type_name = self.__visit_decl_type(node.child_by_field_name("type"))
        decl_node = node.child_by_field_name("declarator")
        if decl_node:
            decl_name, is_func= self._visit_decl_decl(decl_node)
        else:
            field_counter = self.scope_manager.get_scope(self.current_ns).inc_field_counter()
            decl_name = utils.get_field_name(field_counter)
            is_func = False
        deftype = DefType.NAME_DEF
        if is_func:
            deftype = DefType.FUNC_DEF
            if node.type == "field_declaration":
                deftype |= DefType.NAME_DEF
        elif node.type == "type_definition":
            deftype = DefType.TYPE_DEF
        
        decl_def, decl_sc = self._create_def_and_scope(decl_name, deftype, node)
        if deftype & (DefType.NAME_DEF | DefType.TYPE_DEF):
            decl_def.get_name_pointer().add(type_name)
        if deftype & DefType.FUNC_DEF:
            # create return type
            self.name_stack.append(decl_name)
            ret_def, _ = self._create_def_and_scope(RETURN_NAME, DefType.NAME_DEF, None)
            self.name_stack.pop()
            ret_def.get_name_pointer().add(type_name)
            decl_sc.add_def(RETURN_NAME, ret_def)

    def __visit_decl_type(self, node: TSNode) -> str:
        if node.type == "type_identifier":
            return node.text.decode("utf-8").strip()
        elif node.type == "primitive_type":
            return self.visit_primitive_type(node)
        elif node.type == "struct_specifier":
            return self.visit_struct_specifier(node)
        elif node.type == "enum_specifier":
            self.visit(node)
            return "int"
        elif node.type == "union_specifier":
            return self.visit_union_specifier(node)
        
    def __resolve_args(self, node: TSNode) -> List[Tuple[str, str]]:
        cur_node = node
        while not cur_node.type.endswith("function_declarator"):
            cur_node = cur_node.child_by_field_name("declarator")
            if not cur_node:
                return []
        results = []
        params = cur_node.child_by_field_name("parameters")
        for param in params.children:
            if param.type != "parameter_declaration":
                continue
            type_node = param.child_by_field_name("type")
            if not type_node:
                results.append((None, None, None))
                continue
            type_name = self.__visit_decl_type(type_node)
            name_node = param.child_by_field_name("declarator")
            if not name_node:
                results.append((None, None, None))
                continue
            name = self._visit_decl_decl(name_node)[0]
            results.append((name, type_name, param))
        return results

    def __handle_function_def(self, node: TSNode, func_name, ret_type=UNKNOWN_RET_TYPE) -> Definition:
        func_def, func_sc = self._create_def_and_scope(func_name, DefType.FUNC_DEF, node)
        func_ret_ns = utils.join_ns(func_def.get_ns(), RETURN_NAME)
        func_ret_def = self.def_manager.create(func_ret_ns, DefType.NAME_DEF)
        func_ret_def.get_name_pointer().add(ret_type)
        func_sc.add_def(RETURN_NAME, func_ret_def)

        # creaete arg definitions
        func_name_pointer = func_def.get_name_pointer()
        args = self.__resolve_args(node)
        for pos, (arg_name, arg_type, arg_node) in enumerate(args):
            if arg_name is None:
                continue
            arg_ns = utils.join_ns(func_def.get_ns(), arg_name)
            self.scope_manager.create_scope(arg_ns, func_sc, arg_node)
            func_name_pointer.add_pos_arg(pos, arg_name, arg_ns)
            arg_def = self.def_manager.get(arg_ns)
            if not arg_def:
                arg_def = self.def_manager.create(arg_ns, DefType.NAME_DEF)
            arg_def.get_name_pointer().add(arg_type)
            func_sc.add_def(arg_name, arg_def)
        
        return func_def

        