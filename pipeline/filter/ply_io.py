from __future__ import annotations

import io
from pathlib import Path
from typing import Any, BinaryIO
import numpy as np

# Mapping between PLY header property types and numpy dtype codes
PLY_TYPE_TO_NP: dict[str, str] = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "i2",
    "int16": "i2",
    "ushort": "u2",
    "uint16": "u2",
    "int": "i4",
    "int32": "i4",
    "uint": "u4",
    "uint32": "u4",
    "float": "f4",
    "float32": "f4",
    "double": "f8",
    "float64": "f8",
}

NP_TO_PLY_TYPE: dict[str, str] = {
    "i1": "char",
    "u1": "uchar",
    "i2": "short",
    "u2": "ushort",
    "i4": "int",
    "u4": "uint",
    "f4": "float",
    "f8": "double",
}


def parse_ply_header(handle: BinaryIO) -> tuple[dict[str, Any], int]:
    """Parse PLY header and return metadata dict along with byte offset of binary body."""
    header_lines: list[str] = []
    while True:
        line_bytes = handle.readline()
        if not line_bytes:
            raise ValueError("Unexpected EOF before 'end_header' in PLY file")
        line = line_bytes.decode("ascii", errors="replace").strip()
        header_lines.append(line)
        if line == "end_header":
            break

    if not header_lines or header_lines[0] != "ply":
        raise ValueError("Not a valid PLY file (missing 'ply' magic header)")

    fmt: str | None = None
    elements: list[dict[str, Any]] = []
    current_element: dict[str, Any] | None = None

    for line in header_lines[1:]:
        if not line or line.startswith("comment"):
            continue
        parts = line.split()
        if parts[0] == "format":
            fmt = parts[1]
        elif parts[0] == "element":
            current_element = {
                "name": parts[1],
                "count": int(parts[2]),
                "properties": [],
            }
            elements.append(current_element)
        elif parts[0] == "property" and current_element is not None:
            if parts[1] == "list":
                current_element["properties"].append({
                    "kind": "list",
                    "count_type": parts[2],
                    "value_type": parts[3],
                    "name": parts[4],
                })
            else:
                current_element["properties"].append({
                    "kind": "scalar",
                    "type": parts[1],
                    "name": parts[2],
                })

    if fmt != "binary_little_endian":
        raise ValueError(f"Unsupported PLY format: {fmt}. Only 'binary_little_endian' is supported.")

    return {"format": fmt, "elements": elements}, handle.tell()


def read_ply_gaussian(path: Path | str) -> tuple[np.ndarray, dict[str, Any]]:
    """Read a binary little-endian 3DGS PLY file into a numpy structured array."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PLY file does not exist: {path}")

    with path.open("rb") as handle:
        header_meta, data_offset = parse_ply_header(handle)
        vertex_element = next(
            (el for el in header_meta["elements"] if el["name"] == "vertex"), None
        )
        if vertex_element is None:
            raise ValueError(f"PLY file {path} has no 'vertex' element")

        vertex_count = vertex_element["count"]
        props = vertex_element["properties"]

        dtype_fields: list[tuple[str, str]] = []
        for prop in props:
            if prop["kind"] != "scalar":
                raise ValueError(f"List properties in 3DGS vertex element not supported: {prop}")
            ptype = prop["type"]
            if ptype not in PLY_TYPE_TO_NP:
                raise ValueError(f"Unknown PLY type: {ptype}")
            dtype_fields.append((prop["name"], "<" + PLY_TYPE_TO_NP[ptype]))

        struct_dtype = np.dtype(dtype_fields)

        handle.seek(data_offset)
        data = np.fromfile(handle, dtype=struct_dtype, count=vertex_count)

        if len(data) != vertex_count:
            raise ValueError(
                f"Corrupt PLY: expected {vertex_count} vertices, but read {len(data)}"
            )

    return data, header_meta


def write_ply_gaussian(
    path: Path | str,
    data: np.ndarray,
    comments: list[str] | None = None,
) -> None:
    """Write a numpy structured array to a binary little-endian 3DGS PLY file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    vertex_count = len(data)
    dtype = data.dtype

    header_parts = [
        "ply",
        "format binary_little_endian 1.0",
        "comment NammaSpace Filter Pipeline Output",
    ]
    if comments:
        for c in comments:
            header_parts.append(f"comment {c}")

    header_parts.append(f"element vertex {vertex_count}")

    for name in dtype.names or []:
        field_dtype = dtype.fields[name][0]
        # Get base type code (e.g., 'f4', 'u1')
        type_code = field_dtype.str.lstrip("<>=|")
        ply_type = NP_TO_PLY_TYPE.get(type_code, "float")
        header_parts.append(f"property {ply_type} {name}")

    header_parts.append("end_header\n")
    header_str = "\n".join(header_parts)

    with path.open("wb") as handle:
        handle.write(header_str.encode("ascii"))
        data.tofile(handle)
