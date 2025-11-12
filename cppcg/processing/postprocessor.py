from pycg.processing.base import ProcessingBase


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

    def analyze(self):
        # Complete the closure for downstream processors
        # (No Python AST traversal for C)
        self.closured = self.def_manager.transitive_closure()

