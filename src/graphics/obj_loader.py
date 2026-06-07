"""Minimal OBJ file loader — returns GL-ready triangle mesh data."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ObjMesh:
    """Loaded OBJ mesh ready for OpenGL rendering.

    Attributes
    ----------
    verts  : list of (x, y, z) floats
    normals: list of (nx, ny, nz) floats — one per vertex (smooth)
    tris   : list of (i0, i1, i2) int triples — 0-based vertex indices
    """

    __slots__ = ("verts", "normals", "tris")

    def __init__(self, verts, normals, tris):
        self.verts   = verts
        self.normals = normals
        self.tris    = tris

    @property
    def tri_count(self):
        return len(self.tris)


def load_obj(filepath: str) -> Optional[ObjMesh]:
    """Parse an OBJ file and return an ObjMesh, or None on error.

    Supports
    --------
    * ``v x y z``   — geometric vertices
    * ``vn x y z``  — vertex normals
    * ``f v//vn …`` — triangles or quads (v/vt/vn or v//vn)
    """
    try:
        raw_verts   = []  # (x, y, z)
        raw_normals = []  # (nx, ny, nz)
        raw_faces   = []  # list of [(vi, ni), …]  all 1-based

        with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                tok   = parts[0]

                if tok == "v":
                    raw_verts.append(tuple(float(p) for p in parts[1:4]))

                elif tok == "vn":
                    raw_normals.append(tuple(float(p) for p in parts[1:4]))

                elif tok == "f":
                    face = []
                    for item in parts[1:]:
                        segs = item.split("/")
                        vi   = int(segs[0]) - 1           # 0-based
                        ni   = int(segs[2]) - 1 if len(segs) >= 3 and segs[2] else -1
                        face.append((vi, ni))
                    if len(face) >= 3:
                        raw_faces.append(face)

        if not raw_verts or not raw_faces:
            logger.warning("OBJ load: no geometry in %s", filepath)
            return None

        # Build output arrays
        out_verts   = list(raw_verts)
        out_normals = list(raw_normals) if raw_normals else [(0.0, 1.0, 0.0)] * len(raw_verts)

        # Triangulate faces (fan from first vertex)
        out_tris = []
        for face in raw_faces:
            v0, _ = face[0]
            for k in range(1, len(face) - 1):
                v1, _ = face[k]
                v2, _ = face[k + 1]
                out_tris.append((v0, v1, v2))

        logger.info("OBJ loaded: %s — %d verts, %d tris",
                    filepath, len(out_verts), len(out_tris))
        return ObjMesh(out_verts, out_normals, out_tris)

    except Exception as exc:
        logger.error("OBJ load failed (%s): %s", filepath, exc)
        return None
