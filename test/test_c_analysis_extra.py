import os
from pycg.processing.c_analyzer import analyze_c_file_full
from pycg.pycg import CallGraphGenerator


def _disable_ts_build(monkeypatch):
    monkeypatch.setenv("TS_C_DISABLE_BUILD", "1")


def test_direct_and_attr_calls_analyzer(tmp_path, monkeypatch):
    _disable_ts_build(monkeypatch)
    code = r"""
    int g(){ return 1; }
    int h(){ return 2; }
    typedef struct { int (*fp)(); } S;
    int f(){
        S *s; s->fp = h; s->fp();
        g();
        return 0;
    }
    """
    src = tmp_path / "t.c"
    src.write_text(code)

    res = analyze_c_file_full(str(src))

    assert "f.s.fp" in res.assignments
    assert "h" in res.assignments["f.s.fp"], res.assignments

    assert "f" in res.attr_calls
    assert "s.fp" in {x.replace("->", ".") for x in res.attr_calls["f"]}

    assert "f" in res.direct_calls
    assert "g" in res.direct_calls["f"], res.direct_calls
    assert "h" in res.functions and "g" in res.functions and "f" in res.functions


def test_call_graph_pointer_resolution(tmp_path, monkeypatch):
    _disable_ts_build(monkeypatch)
    pkg = tmp_path
    code = r"""
    int target(){ return 0; }
    typedef struct { int (*decode)(); } D;
    int f(){ D *d; d->decode = target; d->decode(); return 0; }
    """
    src = pkg / "mod.c"
    src.write_text(code)

    gen = CallGraphGenerator([str(src)], str(pkg), max_iter=1, operation="call-graph", files_whitelist=[str(src)])
    gen.analyze()
    edges = gen.output_edges()
    # module name is path stem 'mod'
    fn = "mod.f"
    tgt = "mod.target"
    assert [fn, tgt] in edges, edges


def test_nested_field_assignment(tmp_path, monkeypatch):
    _disable_ts_build(monkeypatch)
    code = r"""
    int h(){ return 0; }
    struct X { int (*fp)(); struct { int (*fp)(); } y; };
    int f(){ struct X* s; s->y.fp = h; s->y.fp(); return 0; }
    """
    src = tmp_path / "nested.c"
    src.write_text(code)
    res = analyze_c_file_full(str(src))
    assert "f.s.y.fp" in res.assignments, res.assignments
    assert "h" in res.assignments["f.s.y.fp"], res.assignments

