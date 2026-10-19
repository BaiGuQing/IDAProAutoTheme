import os, sys, json, re, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")
res = {}
try:
    sys.path.insert(0, SRC)
    import IDAAutoTheme as T

    def normalize(txt):
        txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
        decls = []
        for part in re.split(r";", txt):
            p = " ".join(part.split())
            if p:
                decls.append(p)
        return decls

    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance()
    actual = app.styleSheet() or ""
    mine = T.parse_theme(T.theme_search_dirs(), "default").qss

    a, b = normalize(mine), normalize(actual)
    sa, sb = set(a), set(b)
    res["actual_len"] = len(actual)
    res["mine_len"] = len(mine)
    res["decl_mine"] = len(a)
    res["decl_actual"] = len(b)
    res["only_mine"] = [x for x in a if x not in sb]
    res["only_actual"] = [x for x in b if x not in sa]
    res["identical_semantics"] = not res["only_mine"] and not res["only_actual"]

    d = T.parse_theme(T.theme_search_dirs(), "dark")
    res["dark_palette"] = d.palette
    res["dark_qss_len"] = len(d.qss)
except Exception:
    res["err"] = traceback.format_exc()

with open(os.path.join(HERE, "out8.txt"), "w", encoding="utf-8") as f:
    json.dump(res, f, indent=2, ensure_ascii=False)

import ida_kernwin
ida_kernwin.qexit(0)
