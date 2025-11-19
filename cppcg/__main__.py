import argparse
import json

from .formats.simple import Simple
from .formats.as_graph import AsGraph
from .cppcg import CallGraphGenerator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("entry_point", nargs="*", help="Entry points to be processed")
    parser.add_argument(
        "--package", help="Package containing the code to be analyzed", default=None
    )
    parser.add_argument(
        "--max-iter",
        type=int,
        help=(
            "Maximum number of iterations through source code. "
            "If not specified a fix-point iteration will be performed."
        ),
        default=-1,
    )

    parser.add_argument(
        "--as-graph-output", help="Output for the assignment graph", default=None
    )
    parser.add_argument("-o", "--output", help="Output path", default=None)

    args = parser.parse_args()

    cg = CallGraphGenerator(
        args.entry_point, args.package, args.max_iter
    )
    cg.analyze()

    formatter = Simple(cg)
    output = formatter.generate()

    as_formatter = AsGraph(cg)

    if args.output:
        with open(args.output, "w+") as f:
            f.write(json.dumps(output))
    else:
        print(json.dumps(output))

    if args.as_graph_output:
        with open(args.as_graph_output, "w+") as f:
            f.write(json.dumps(as_formatter.generate()))


if __name__ == "__main__":
    main()
