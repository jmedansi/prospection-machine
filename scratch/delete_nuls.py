import os
from pathlib import Path

def clean_nul_files_aggressive(root_dir):
    root_path = Path(root_dir).resolve()
    deleted_count = 0
    all_dirs = []
    for dirpath, dirnames, filenames in os.walk(str(root_path)):
        all_dirs.append(dirpath)
        
    print(f"Checking {len(all_dirs)} directories...")
    for d in all_dirs:
        for name in ['nul', 'NUL']:
            p = os.path.join(d, name)
            unc_path = "\\\\?\\" + p
            try:
                # Try to remove as file
                os.remove(unc_path)
                print(f"Deleted file: {p}")
                deleted_count += 1
            except FileNotFoundError:
                pass
            except PermissionError:
                # Could be a directory
                try:
                    os.rmdir(unc_path)
                    print(f"Deleted folder: {p}")
                    deleted_count += 1
                except Exception as dir_e:
                    print(f"Failed to delete directory {p}: {dir_e}")
            except Exception as e:
                # Let's see if we can do rmdir
                try:
                    os.rmdir(unc_path)
                    print(f"Deleted folder: {p}")
                    deleted_count += 1
                except Exception:
                    pass
                
    print(f"Total deleted: {deleted_count}")

if __name__ == '__main__':
    clean_nul_files_aggressive("d:\\prospection-machine")
