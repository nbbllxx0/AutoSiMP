from __future__ import annotations

import argparse
import os
import sys
import tempfile
import uuid
from pathlib import Path


def patch_tempdir(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    cache = base / "cupy_cache"
    cache.mkdir(parents=True, exist_ok=True)

    os.environ["TEMP"] = str(base)
    os.environ["TMP"] = str(base)
    os.environ["TMPDIR"] = str(base)
    os.environ["CUPY_CACHE_DIR"] = str(cache)
    tempfile.tempdir = str(base)

    cuda13 = Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0")
    if cuda13.exists():
        os.environ["CUDA_PATH"] = str(cuda13)
        os.environ["CUDA_HOME"] = str(cuda13)
        cuda_bin = str(cuda13 / "bin")
        path_parts = os.environ.get("PATH", "").split(os.pathsep)
        if cuda_bin not in path_parts:
            os.environ["PATH"] = os.pathsep.join([cuda_bin, *path_parts])

    class PersistentTemporaryDirectory:
        def __init__(
            self,
            suffix: str | None = None,
            prefix: str | None = None,
            dir: str | None = None,
            ignore_cleanup_errors: bool = False,
        ) -> None:
            root = Path(dir) if dir else base
            name = f"{prefix or 'td_'}{uuid.uuid4().hex}{suffix or ''}"
            self.name = str(root / name)
            os.makedirs(self.name, exist_ok=True)

        def __enter__(self) -> str:
            return self.name

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def cleanup(self) -> None:
            return None

    tempfile.TemporaryDirectory = PersistentTemporaryDirectory  # type: ignore[assignment]


def cupy_smoke() -> None:
    import cupy as cp

    print(f"cupy={cp.__version__}")
    print(f"cuda_runtime={cp.cuda.runtime.runtimeGetVersion()}")
    print(f"devices={cp.cuda.runtime.getDeviceCount()}")
    props = cp.cuda.runtime.getDeviceProperties(0)
    print(f"device0={props['name'].decode()}")
    x = cp.arange(8, dtype=cp.float32)
    cp.cuda.Stream.null.synchronize()
    print(f"sum_square={float((x * x).sum().get())}")


def topogpu_cli(args: list[str]) -> None:
    if args and args[0] == "verify":
        topogpu_verify(args[1:])
        return

    from topogpu.cli import main

    sys.argv = ["topogpu", *args]
    raise SystemExit(main())


def topogpu_verify(args: list[str]) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="rerun_outputs/topogpu_verify")
    parser.add_argument("--case", default="tool_long_cantilever_vf16")
    parser.add_argument("--dims", default="6x4x4")
    parser.add_argument("--small", action="store_true")
    ns = parser.parse_args(args)

    dims = "6x4x4" if ns.small else ns.dims
    out_path = Path(ns.out)
    if not out_path.is_absolute():
        out_path = (Path.cwd() / out_path).resolve()

    import topogpu

    root = Path(topogpu.__file__).resolve().parents[2]
    src = root / "src"
    for path in (root, src):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    from experiments.tool_paper import verify_numerics

    verify_numerics.ROOT = Path.cwd().resolve()
    sys.argv = [
        "verify_numerics.py",
        "--out",
        str(out_path),
        "--case-dim",
        f"{ns.case}={dims}",
    ]
    raise SystemExit(verify_numerics.main())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--temp-base",
        default=None,
        help="Writable persistent temp/cache root for CuPy NVRTC compilation. Defaults to ./tmp/topogpu_tmp_open.",
    )
    parser.add_argument("--cupy-smoke", action="store_true")
    parser.add_argument("--topogpu", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    temp_base = Path(args.temp_base) if args.temp_base else Path.cwd() / "tmp" / "topogpu_tmp_open"
    patch_tempdir(temp_base)
    print(f"tempfile={tempfile.gettempdir()}")

    if args.cupy_smoke:
        cupy_smoke()
    if args.topogpu:
        topogpu_cli(args.topogpu)


if __name__ == "__main__":
    main()
