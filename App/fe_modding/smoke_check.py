"""Exercise packaged resources without a game dump or a system Python."""
import importlib
import json
from pathlib import Path
import pkgutil
import traceback


def run(report_path):
    report = {"ok": False}
    window = None
    try:
        import fe_modding
        import numpy as np
        from PIL import Image
        import sv_ttk
        from fontTools.ttLib import TTFont
        import wgpu.backends.wgpu_native
        # Import all application modules, including lazily opened viewers.
        for info in pkgutil.walk_packages(fe_modding.__path__, "fe_modding."):
            if not info.name.endswith(".__main__"):
                importlib.import_module(info.name)
        catalog = Path(__file__).parent / "formats" / "cmb" / "externs_fe9.json"
        assert json.loads(catalog.read_text(encoding="utf-8"))["externs"]
        assert np.asarray(Image.new("RGBA", (2, 2))).shape == (2, 2, 4)
        from .gui.app import MainWindow
        window = MainWindow()
        window.withdraw()
        window.update_idletasks()
        assert window.tk.call("ttk::style", "theme", "use").startswith("sun-valley")
        report.update(ok=True, tkinter=window.tk.call("info", "patchlevel"), catalog=True,
                      numpy=np.__version__, gpu_library=True, fonttools=TTFont.__name__)
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if window is not None:
            window.destroy()
    Path(report_path).write_bytes((json.dumps(report, indent=2) + "\n").encode("utf-8"))
    return 0 if report["ok"] else 1
