"""Configuration words -> addressed frames -> Project X-Ray FASM."""

import argparse
import hashlib
import json
from pathlib import Path

from frames import decode_frames, load_part, to_bitdata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--db-root", default="third_party/prjxray-db/artix7")
    parser.add_argument("--part", default="xc7a35tcpg236-1")
    args = parser.parse_args()
    import fasm
    import fasm.output
    from prjxray.db import Database
    from prjxray.fasm_disassembler import FasmDisassembler

    data = args.input.read_bytes()
    frames, report = decode_frames(data, load_part(args.db_root, args.part))
    db = Database(args.db_root, args.part)
    disassembler = FasmDisassembler(db)
    features = list(disassembler.find_features_in_bitstream(to_bitdata(frames), verbose=True))
    report["unknown_bits"] = sum(
        any(a.name == "unknown_bit" for a in (line.annotations or ())) for line in features)
    report["missing_tile_types"] = sorted(disassembler.decode_warnings)
    report["features"] = sum(line.set_feature is not None for line in features)
    report["sha256"] = hashlib.sha256(data).hexdigest()
    report["input"] = str(args.input)
    report["part"] = args.part
    report["scope"] = "unencrypted, uncompressed full configuration; no CRC validation"
    model = fasm.output.merge_and_sort(features, zero_function=disassembler.is_zero_feature,
                                       sort_key=db.grid().tile_key)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(fasm.fasm_tuple_to_string(model))
    args.output.with_suffix(".decode.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
