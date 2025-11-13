from .base import ProcessingBase
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode


class PostProcessor(ProcessingBase):
    def __init__(
        self,
        input_file,
        modname,
        import_manager,
        scope_manager,
        def_manager,
        class_manager,
        module_manager,
        modules_analyzed=None,
    ):
        super().__init__(input_file, modname, modules_analyzed)
        self.import_manager = import_manager
        self.scope_manager = scope_manager
        self.def_manager = def_manager
        self.class_manager = class_manager
        self.module_manager = module_manager

    def visit_assignment_expression(self, node: TSNode):
        super()._visit_assignment_expression(node)

    def visit_call_expression(self, node: TSNode):
        pass

    def visit_function_definition(self, node: TSNode):
        pass
        
    def _visit_assignment_expression(self, node: TSNode):
        pass

    def visit_return_statement(self, node: TSNode):
        pass