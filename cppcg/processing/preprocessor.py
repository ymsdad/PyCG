import os

from pycg import utils
from .base import ProcessingBase
from .c_analyzer import analyze_c_file_full
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

class PreProcessor(ProcessingBase):
    def __init__(
        self, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)

    def visit_function_definition(self, node: TSNode):
        
        super().visit_function_definition(node)

    def visit_type_definition(self, node: TSNode):
        pass

    def __handle_function_def(self, node: TSNode):
        func_name = self.__extract_func_def_name(node)
        current_def = self.def_manager.get(self.current_ns)
        