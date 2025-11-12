from typing import Dict, Set
import os

CPP_SUFFIX = (".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx", ".c++", ".h++", ".cuh", ".cu")

class FileManager(object):
    def __init__(self, basedir: str):
        self.basedir = basedir
        self.imports: Dict[str, Set[str]] = {}
        self.__scan_dir(basedir)

    def __scan_dir(self, basedir: str):
        for root, _, files in os.walk(basedir):
            for file in files:
                if file.endswith(CPP_SUFFIX):
                    file_abs = os.path.join(root, file)
                    file_rel = os.path.relpath(file_abs, basedir)
                    self.imports[file_rel] = set()

    def file_abs_path(self, filename):
        return os.path.abspath(os.path.join(self.basedir, filename))
    
    def add_import(self, module_name, file_name):
        if module_name not in self.imports:
            self.imports[module_name] = set()
        self.imports[module_name].add(file_name)