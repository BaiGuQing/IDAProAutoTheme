import os, sys, json, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
res = {}
try:
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance()
    for _ in range(40):
        QtCore.QCoreApplication.processEvents()

    res["qss_len"] = len(app.styleSheet() or "")
    res["modules"] = sorted(m for m in sys.modules if "AutoTheme" in m)

    main = None
    for w in app.topLevelWidgets():
        if isinstance(w, QtWidgets.QMainWindow) and w.isWindow():
            main = w
            break

    def walk(menu, depth, out):
        for act in menu.actions():
            txt = act.text().replace("&", "")
            sub = act.menu()
            if sub is not None:
                out.append("  " * depth + "[%s]" % txt)
                walk(sub, depth + 1, out)
            elif txt:
                out.append("  " * depth + txt)

    lines = []
    if main is not None:
        mb = main.menuBar()
        for act in mb.actions():
            m = act.menu()
            if m is not None and "Edit" in act.text():
                walk(m, 0, lines)
    res["edit_menu"] = lines
    res["has_auto_theme"] = any("Auto Theme" in l for l in lines)
except Exception:
    res["err"] = traceback.format_exc()

with open(os.path.join(HERE, "out10.txt"), "w", encoding="utf-8") as f:
    json.dump(res, f, indent=2, ensure_ascii=False)

import ida_kernwin
ida_kernwin.qexit(0)
