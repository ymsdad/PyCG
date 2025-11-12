import os

from pycg.processing.c_analyzer import analyze_c_file


def test_decoder_decode_assignment():
    here = os.path.dirname(__file__)
    repo_root = os.path.abspath(os.path.join(here, os.pardir))
    src = os.path.join(repo_root, "benchmarks", "micro-benchmark", "case1.c")

    mapping = analyze_c_file(src)

    key = "PyImaging_Jpeg2KDecoderNew.decoder.decode"
    assert key in mapping, f"missing key {key}. Available keys: {sorted(mapping.keys())}"
    assert "ImagingJpeg2KDecode" in mapping[key]

