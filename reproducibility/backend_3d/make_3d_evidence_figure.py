from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import pyvista as pv
from skimage import measure


HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results_3d_large" / "runs"
FIGURES = HERE.parent / "figures"

CASES = [
    ("cantilever_z_27k_vf30_i6", "27k elems"),
    ("cantilever_z_64k_vf30_i6", "64k elems"),
    ("cantilever_z_216k_vf30_i6", "216k elems"),
]


ISO_LEVEL = 0.60
RENDER_SIZE = (1400, 900)
SURFACE_COLOR = (0.62, 0.62, 0.64)


def load_case(case_id: str) -> tuple[np.ndarray, tuple[int, int, int], dict]:
    run_dir = RESULTS / case_id
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    problem = summary["problem"]
    dims = (int(problem["nelx"]), int(problem["nely"]), int(problem["nelz"]))
    rho = np.load(run_dir / "rho_final.npy").reshape(dims)
    return rho, dims, summary


def density_to_mesh(rho: np.ndarray) -> pv.PolyData:
    padded = np.pad(rho, 1, mode="constant", constant_values=0.0)
    verts, faces, _, _ = measure.marching_cubes(
        padded,
        level=ISO_LEVEL,
        allow_degenerate=False,
    )
    verts -= 1.0
    faces_pv = np.hstack(
        [
            np.full((faces.shape[0], 1), 3, dtype=np.int64),
            faces.astype(np.int64),
        ]
    ).ravel()
    mesh = pv.PolyData(verts.astype(np.float32), faces_pv)
    mesh = mesh.smooth_taubin(
        n_iter=8,
        pass_band=0.12,
        feature_smoothing=False,
        boundary_smoothing=False,
        non_manifold_smoothing=False,
    )
    return mesh.compute_normals(
        auto_orient_normals=True,
        consistent_normals=True,
        feature_angle=30.0,
    )


def render_mesh(mesh: pv.PolyData, out_png: Path) -> None:
    plotter = pv.Plotter(off_screen=True, window_size=RENDER_SIZE)
    plotter.set_background("white")
    plotter.add_mesh(
        mesh,
        color=SURFACE_COLOR,
        smooth_shading=True,
        specular=0.18,
        specular_power=14.0,
        diffuse=0.95,
        ambient=0.24,
        show_edges=False,
    )

    xmin, xmax, ymin, ymax, zmin, zmax = mesh.bounds
    cx, cy, cz = 0.5 * (xmin + xmax), 0.5 * (ymin + ymax), 0.5 * (zmin + zmax)
    lx, ly, lz = xmax - xmin, ymax - ymin, zmax - zmin
    radius = 2.4 * max(lx, ly, lz)
    plotter.camera.position = (cx + 0.72 * radius, cy - 0.86 * radius, cz + 0.58 * radius)
    plotter.camera.focal_point = (cx, cy, cz)
    plotter.camera.up = (0.0, 0.0, 1.0)
    plotter.enable_parallel_projection()
    plotter.reset_camera()
    plotter.camera.zoom(1.18)

    plotter.remove_all_lights()
    for position, intensity in [
        ((cx + radius, cy - 0.5 * radius, cz + 1.2 * radius), 0.95),
        ((cx - 1.2 * radius, cy + 0.4 * radius, cz + 0.6 * radius), 0.45),
        ((cx - 0.3 * radius, cy - 1.1 * radius, cz + 1.4 * radius), 0.35),
    ]:
        plotter.add_light(
            pv.Light(
                position=position,
                focal_point=(cx, cy, cz),
                color="white",
                intensity=intensity,
                light_type="scene light",
            )
        )
    plotter.enable_anti_aliasing("ssaa")
    plotter.screenshot(out_png, transparent_background=False, return_img=False)
    plotter.close()


def trim_white(img: Image.Image, pad: int = 16) -> Image.Image:
    gray = img.convert("L")
    mask = gray.point(lambda p: 255 if p < 248 else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return img
    left = max(bbox[0] - pad, 0)
    top = max(bbox[1] - pad, 0)
    right = min(bbox[2] + pad, img.width)
    bottom = min(bbox[3] + pad, img.height)
    return img.crop((left, top, right, bottom))


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    tmp_dir = FIGURES / "_3d_backend_renders"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    panels: list[tuple[str, Path, tuple[int, int, int], dict]] = []
    for case_id, label in CASES:
        rho, dims, summary = load_case(case_id)
        render_path = tmp_dir / f"{case_id}_isosurface.png"
        render_mesh(density_to_mesh(rho), render_path)
        panels.append((label, render_path, dims, summary))

    fig, axes = plt.subplots(1, len(panels), figsize=(8.4, 2.75), facecolor="white")
    if len(panels) == 1:
        axes = [axes]
    for ax, (label, png, dims, summary) in zip(axes, panels):
        final = summary["final"]
        img = trim_white(Image.open(png).convert("RGB"))
        ax.imshow(img)
        ax.set_axis_off()
        ax.set_title(
            f"{label}\n{dims[0]}x{dims[1]}x{dims[2]}, C={final['compliance']:.2f}, gray={final['grayness']:.3f}",
            fontsize=7.5,
            pad=3,
        )
    fig.tight_layout(pad=0.2)
    out_png = FIGURES / "fig_3d_backend_evidence.png"
    out_pdf = FIGURES / "fig_3d_backend_evidence.pdf"
    fig.savefig(out_png, dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(out_pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(out_png)
    print(out_pdf)


if __name__ == "__main__":
    main()
