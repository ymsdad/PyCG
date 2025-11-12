import os

from pycg.processing.base import ProcessingBase
from .c_analyzer import analyze_c_file_full


class CallGraphProcessor(ProcessingBase):
    def __init__(
        self,
        filename,
        modname,
        import_manager,
        scope_manager,
        def_manager,
        class_manager,
        module_manager,
        call_graph=None,
        modules_analyzed=None,
    ):
        super().__init__(filename, modname, modules_analyzed)

        self.import_manager = import_manager
        self.scope_manager = scope_manager
        self.def_manager = def_manager
        self.class_manager = class_manager
        self.module_manager = module_manager

        self.call_graph = call_graph

    def analyze(self):
        # C-only analysis using Tree-sitter results provided by preprocessor
        res = analyze_c_file_full(self.filename)

        # 1) Edges for pointer assignments: Func -> RHS symbols
        for dotted_lhs, rhs_set in res.assignments.items():
            func_name = dotted_lhs.split(".")[0]
            func_ns = f"{self.modname}.{func_name}" if self.modname else func_name
            if self.call_graph:
                self.call_graph.add_node(func_ns, self.modname)
            for rhs in rhs_set:
                rhs_ns = f"{self.modname}.{rhs}" if self.modname else rhs
                if self.call_graph:
                    self.call_graph.add_node(rhs_ns, self.modname)
                    self.call_graph.add_edge(func_ns, rhs_ns)

        # 2) Direct function calls: Func -> callee
        for func_name, callees in res.direct_calls.items():
            func_ns = f"{self.modname}.{func_name}" if self.modname else func_name
            if self.call_graph:
                self.call_graph.add_node(func_ns, self.modname)
            for callee in callees:
                callee_ns = f"{self.modname}.{callee}" if self.modname else callee
                if self.call_graph:
                    self.call_graph.add_node(callee_ns, self.modname)
                    self.call_graph.add_edge(func_ns, callee_ns)

        # 3) Attribute calls via function pointers: resolve through defs
        #    We expect PreProcessor+PostProcessor to have created closures for
        #    names like mod.fn.decoder.decode -> {mod.Target}
        for func_name, dotted_attrs in res.attr_calls.items():
            func_ns = f"{self.modname}.{func_name}" if self.modname else func_name
            if self.call_graph:
                self.call_graph.add_node(func_ns, self.modname)
            for attr in dotted_attrs:
                ns = f"{func_ns}.{attr.replace('->','.')}"
                defi = self.def_manager.get(ns)
                if not defi:
                    continue
                # If this name points to any known functions, add edges
                for target in defi.get_name_pointer().get():
                    if self.call_graph:
                        self.call_graph.add_node(target, self.modname)
                        self.call_graph.add_edge(func_ns, target)
