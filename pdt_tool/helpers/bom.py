import argparse
import os
import platform
import stat
import subprocess
import tempfile

repo_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
execution_dir = os.getcwd()


def parse_args():
    ######################################################################################################
    # Define a parser for generating BOM file
    ######################################################################################################
    parser = argparse.ArgumentParser(description="Tool to assist with generating BOMs for components")
    parser.add_argument('--bom-path', '-b',
                        required=True,
                        help="Path for generated BOM file.")
    parser.add_argument('--component-dir', '-cd',
                        required=True,
                        help="Path to the folder containing the fileset to drop.")

    _args = parser.parse_args()
    component_dir = _args.component_dir
    full_component_dir_path = os.path.join(execution_dir, _args.component_dir)
    if os.path.exists(full_component_dir_path):
        _args.component_dir = full_component_dir_path
    elif not os.path.exists(component_dir) or not os.path.isdir(component_dir):
        parser.error(f"Component dir provided `{component_dir}` does not exist or is not a dir.")
    return _args


def is_windows():
    return platform.system() == "Windows"


def get_cksum_bin():
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), "resources", "cksum.exe")


def is_local_cksum_functional():
    """
    We ship a `cksum.exe` file in the resources folder of this repo to be used on Windows. The performance is very good
    however it has dependencies on .NET and other C++ redistributables.
    We also have a pure python implementation of `cksum` in `helpers/py_cksum.py` which works always but is 9x slower
    than the `cksum.exe` program.
    This function writes a dummy file and checks if the cksum.exe is able to compute its checksum.
    """
    with tempfile.TemporaryDirectory() as tmp:
        dummy_file = os.path.join(tmp, "dummy")
        with open(dummy_file, "w") as f:
            f.write("dummy")
        try:
            cksum_bin = get_cksum_bin()
            cksum = subprocess.check_output(f'"{cksum_bin}" "{dummy_file}"', shell=True).decode("utf-8").strip()
            expected_cksum = "3723871108"
            if cksum != expected_cksum:
                print(f"Local `cksum.exe` returned `{cksum}` but we expected `{expected_cksum}`. "
                      f"Falling back to python implementation.")
                return False
        except Exception as e:
            print("Failed to compute checksum using the local `cksum.exe` command. "
                  f"Falling back to python implementation. Original error: {e}")
            return False
    return True


def get_file_permission(file_path):
    return oct(stat.S_IMODE(os.stat(file_path).st_mode))[-3:]


def generate_bom_for_path(path, bom_file, owner="oneAPI_CI"):
    if not os.path.exists(path):
        raise Exception(f"Could not generate BOM file. Path `{path}` does not exist.")

    bom_content = "DeliveryName\tInstallName\tFileCheckSum\tOwner\tDescription\tFileOrigin\tInstalledFilePermission\n"

    if is_windows():
        all_files = sorted([os.path.join(root, f) for root, _, files in os.walk(path) for f in files])
        files_checksums = dict()

        if is_local_cksum_functional():
            file_list = os.path.join(execution_dir, "file_list.txt")
            out_file = os.path.join(execution_dir, "cksum_out.txt")

            try:
                with open(file_list, "w") as f:
                    f.write("\n".join(all_files))

                cksum_bin = get_cksum_bin()
                subprocess.check_call([cksum_bin, "-b", file_list, "-o", out_file])

                with open(out_file, "r") as f:
                    stdout = f.read().split("\n")

                for line in sorted(stdout):
                    if not line:
                        continue
                    file_path, cksum = line.split("\t")
                    files_checksums[file_path] = cksum
            finally:
                if os.path.exists(file_list):
                    os.remove(file_list)
                if os.path.exists(out_file):
                    os.remove(out_file)
        else:
            try:
                import py_cksum
            except:
                from helpers import py_cksum
            for file in all_files:
                files_checksums[file] = py_cksum.calculate_cksum(file)

        for file_path in all_files:
            perm = get_file_permission(file_path)
            cksum = files_checksums[file_path]
            name = file_path.replace(path, "").replace("\\", "/").strip("/")

            bom_content += f"<deliverydir>/{name}\t<installdir>/{name}\t{cksum}\t{owner}\t\tInternal\t{perm}\n"
    else:
        if "darwin" in platform.system().lower():
            xargs = "xargs -I{} cksum {}"
        else:
            xargs = "xargs -d '\\n' cksum"

        cmd = f"find '{path}' -type l -or -type f | sort | {xargs}"
        stdout = subprocess.check_output(cmd, shell=True).decode("utf-8").strip().split("\n")
        for line in stdout:
            parts = line.split(" ", 2)

            file_path = parts[2]
            perm = get_file_permission(file_path)
            name = file_path.replace(path, "").replace("\\", "/").strip("/")
            cksum = parts[0]

            bom_content += f"<deliverydir>/{name}\t<installdir>/{name}\t{cksum}\t{owner}\t\tInternal\t{perm}\n"

    bom_content += "#***Intel Confidential - Internal Use Only***"

    bom_parent_dir = os.path.dirname(bom_file)
    if bom_parent_dir:
        os.makedirs(bom_parent_dir, exist_ok=True)
    with open(bom_file, "w") as f:
        f.write(bom_content)


def main():
    args = parse_args()
    generate_bom_for_path(args.component_dir, args.bom_path)


if __name__ == "__main__":
    main()
