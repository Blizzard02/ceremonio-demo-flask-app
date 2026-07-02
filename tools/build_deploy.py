"""Build ceremio_deploy.zip with Linux-friendly forward-slash entry paths."""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP_PATH = os.path.join(ROOT, "ceremio_deploy.zip")

INCLUDE_FILES = ["app.py", "wsgi.py", "requirements.txt"]
INCLUDE_DIRS = ["static", "templates", "translations"]
SKIP_PARTS = {"__pycache__"}
# Don't ship the local sqlite db or per-user uploads in the code bundle.
SKIP_EXT = {".pyc"}


def rel_posix(full):
    return os.path.relpath(full, ROOT).replace(os.sep, "/")


def main():
    if os.path.exists(ZIP_PATH):
        os.remove(ZIP_PATH)

    names = []
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for f in INCLUDE_FILES:
            p = os.path.join(ROOT, f)
            if os.path.exists(p):
                z.write(p, f)
                names.append(f)
        for d in INCLUDE_DIRS:
            base = os.path.join(ROOT, d)
            for dirpath, dirs, files in os.walk(base):
                dirs[:] = [x for x in dirs if x not in SKIP_PARTS]
                for fn in files:
                    if os.path.splitext(fn)[1] in SKIP_EXT:
                        continue
                    full = os.path.join(dirpath, fn)
                    rel = rel_posix(full)
                    z.write(full, rel)
                    names.append(rel)

    bad = [x for x in names if "\\" in x]
    print("entries:", len(names))
    print("backslash paths:", len(bad))
    print("size KB:", round(os.path.getsize(ZIP_PATH) / 1024, 1))
    for key in ["app.py", "templates/settings.html", "templates/invite.html",
                "static/app.css", "translations/el.json", "translations/en.json"]:
        print(f"  has {key}:", key in names)


if __name__ == "__main__":
    main()
