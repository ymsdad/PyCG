

from typing import Dict

class FuncManager:
    DEC = 1
    DEF = 2
    def __init__(self):
        # func -> {file: type}
        self.func2files: Dict[str, Dict[str, int]] = {}
        # file -> {func: type}
        self.files2func: Dict[str, Dict[str, int]] = {}

    def add_func(self, func_name, file_name, func_type):
        if func_name not in self.func2files:
            self.func2files[func_name] = {}
        if file_name not in self.func2files[func_name]:
            self.func2files[func_name][file_name] = 0
        self.func2files[func_name][file_name] |= func_type

        if file_name not in self.files2func:
            self.files2func[file_name] = {}
        if func_name not in self.files2func[file_name]:
            self.files2func[file_name][func_name] = 0
        self.files2func[file_name][func_name] |= func_type

    def merge_func(self, from_file, to_file):
        if from_file not in self.files2func:
            return
        for func_name, func_type in self.files2func[from_file].items():
            self.add_func(func_name, to_file, func_type)