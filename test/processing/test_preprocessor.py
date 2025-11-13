import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cppcg"))

test_code1 = """

typedef struct {
    int x;
    int y;
} Point;

Point p;
Point *init(int x, int y) {
    Point *new_point = malloc(sizeof(Point));
    new_point->x = x;
    new_point->y = y;
    return new_point;
}
"""
from processing.preprocessor import PreProcessor
from machinery.definitions import DefinitionManager
from machinery.scopes import ScopeManager

def test_preprocessor():
    def_manager = DefinitionManager()
    scope_manager = ScopeManager()
    preprocessor = PreProcessor(None, def_manager, None, None, scope_manager)
    preprocessor.analyze_code(test_code1)
    print(1)