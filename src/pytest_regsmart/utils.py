import os


def _find_py_files(working_dir: str) -> list[str]: #mudar para utils talvez 
    excludes = [".venv", ".git", "__pycache__", "dist", "build", "venv", "site-packages"]

    py_files = []
    for dirpath, dirnames, filenames in os.walk(working_dir):
        dirnames[:] = [d for d in dirnames if d not in excludes and not d.endswith(".egg-info")]  # keep only core directories to check
        for filename in filenames:
            if filename.endswith(".py"):
                py_files.append(os.path.join(dirpath, filename)) #build the full path
    return py_files


def _is_test_file(filepath: str) -> bool: #mudar para utils
    filename = os.path.basename(filepath)
    return filename.startswith("test_") or filename.endswith("_test.py")
