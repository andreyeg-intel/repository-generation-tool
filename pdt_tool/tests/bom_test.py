import shutil

from helpers.bom import *


def create_file(name, content, permissions):
    with open(name, "w") as f:
        f.write(content)
    os.chmod(name, permissions)


def test_generate_bom_outputs_expected_result():
    test_folder = "test_folder"
    nested_folder = f"{test_folder}/nested_folder"
    output_bom = os.path.join("bom_dir", "bom.txt")
    try:
        if os.path.exists(test_folder):
            shutil.rmtree(test_folder)
        os.makedirs(nested_folder)

        # Create some folders, files, and symlinks with different permissions and content
        create_file(os.path.join(test_folder, "file1.txt"), "test1", 0o777)
        create_file(os.path.join(test_folder, "file2.txt"), "test2", 0o644)
        create_file(os.path.join(test_folder, "file3.txt"), "test3", 0o771)
        create_file(os.path.join(nested_folder, "file4.txt"), "test4", 0o644)
        create_file(os.path.join(nested_folder, "file5.txt"), "test5", 0o654)
        os.symlink("file1.txt", os.path.join(test_folder, "file1_symlink.txt"))

        generate_bom_for_path(test_folder, output_bom)

        with open(output_bom) as f:
            bom_content = f.read().strip()

        expected_bom = "tests/resources/expected_bom.txt"
        with open(expected_bom) as f:
            expected_bom_content = f.read().strip()

        assert set(bom_content.split("\n")) == set(expected_bom_content.split("\n"))
    finally:
        shutil.rmtree(test_folder)
        shutil.rmtree("bom_dir")
