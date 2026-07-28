"""Command-line entry point: python -m pc2dbt <mapping.xml> -o <out_dir>"""

import argparse
import pathlib

from pc2dbt.emitter import emit_model
from pc2dbt.parser import parse_mapping


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xml_path", help="Path to a PowerCenter mapping XML export")
    parser.add_argument("-o", "--out-dir", default="out", help="Directory to write the generated .sql file into")
    args = parser.parse_args()

    mapping = parse_mapping(args.xml_path)
    sql = emit_model(mapping)

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{mapping.target.name}.sql"
    out_path.write_text(sql)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
