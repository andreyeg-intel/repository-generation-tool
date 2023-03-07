import logging
import os
import re
import shutil
import tarfile
import tempfile
import time

import requests
import urllib3
from artifactory import ArtifactoryPath
from dohq_artifactory.exception import ArtifactoryException

urllib3.disable_warnings()

forbidden_key_chars = "(){}[]*+^$/\\~`!@%&,<>;= "


def sort_list_naturally(list_to_sort, reverse=False, key=None):
    """
    Sorts a list with considering consecutive digits as a single int.

    The way this function works is that it splits each string in the list into another list grouping consecutive digits
    together and anything else together then sorting the initial list accordingly. For example, if the list to be sorted
    contains the strings
    [
        "something-123/something_else.1.2.211",
        "something-2/something_else.1.2.0",
    ]
    then this function will split generate the following list
    [
        ["something-", 123, "/something_else.", 1, ".", 2, ".", 211], # Notice that the numbers are not strings here!
        ["something-", 2, "/something_else.", 1, ".", 2, ".", 0],
    ]
    then when sorting the 2 sub-lists, each item will be compared to its corresponding index in the other list where
    numbers will be sorted correctly.
    """
    key = key or str
    return sorted(list_to_sort,
                  key=lambda x: [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", key(x).replace('_', '.'))],
                  reverse=reverse)


def validate_properties(properties: dict):
    if not properties:
        return
    for key, _ in properties.items():
        if any(i in key for i in forbidden_key_chars):
            raise Exception(f"Invalid characters found in property key `{key}`.")


class ArtifactoryHelper:
    def __init__(self, username: str, password: str, artifactory_url=None, artifactory_repository=None, verbose=False):
        self.artifactory_url = artifactory_url or "https://ubit-artifactory-or.intel.com/artifactory"
        self.repository = artifactory_repository or "satgoneapi-or-local"
        self.repository_url = f"{self.artifactory_url}/{self.repository}"
        self.retry_count = 10
        self.retry_sleep = 30

        session = requests.Session()
        session.auth = (username, password)
        self.session = session

        # 200MB
        self.chunk_size = 200 * 1024 * 1024

        if verbose:
            logging.basicConfig()
            logging.getLogger("artifactory").setLevel(logging.DEBUG)

    def _get_path(self, path):
        path = path.replace("\\", "/")
        path = re.sub("^/+", "", path)
        return ArtifactoryPath(f"{self.repository_url}/{path}", session=self.session)

    def get_path_properties(self, path: str) -> dict:
        """
        Gets all the properties for the specified file in Artifactory
        :param path the full Artifactory file path starting with the repository name
        :return a dictionary with all the file properties
        """
        artifactory_path = self._get_path(path)
        properties = dict()

        error = None
        for retry in range(self.retry_count):
            error = None
            try:
                properties = artifactory_path.properties
                break
            except Exception as e:
                error = e
                print(f"Failed to retrieve properties of `{path}`. Error: {e}")
                time.sleep(self.retry_sleep)

        if error:
            raise error

        return properties

    def set_path_properties(self, path, properties: dict):
        if not properties:
            return

        # Properties values should be strings or array of strings
        actual_properties = dict()
        for k, v in properties.items():
            k = str(k)
            if isinstance(v, list) or isinstance(v, set):
                actual_properties[k] = [str(i) for i in v]
            else:
                actual_properties[k] = str(v)
        validate_properties(actual_properties)

        artifactory_path = self._get_path(path)

        error = None
        for retry in range(self.retry_count):
            error = None
            try:
                artifactory_path.update_properties(properties=actual_properties, recursive=True)
                break
            except Exception as e:
                error = e
                print(f"Failed to set properties for `{path}`. Error: {e}")
                time.sleep(self.retry_sleep)

        if error:
            raise error

    def delete_path(self, path):
        artifactory_path = self._get_path(path)

        error = None
        for retry in range(self.retry_count):
            error = None
            try:
                if artifactory_path.exists():
                    artifactory_path.unlink()
                break
            except Exception as e:
                error = e
                print(f"Failed to delete path `{path}`. Error: {e}")
                time.sleep(self.retry_sleep)

        if error:
            raise error

    def upload(self, path_to_upload, upload_path, properties=None, delete_target_first=True):
        if not path_to_upload:
            return
        validate_properties(properties)

        if not os.path.exists(path_to_upload):
            raise Exception(f"Cannot upload path `{path_to_upload}` since it does not exist")

        if delete_target_first:
            self.delete_path(upload_path)

        original_path_to_upload = path_to_upload
        explode = False
        mkdir = False
        with tempfile.TemporaryDirectory() as temp_dir:
            if os.path.isdir(path_to_upload):
                tarball = os.path.join(temp_dir, "archive.tar.gz")
                with tarfile.open(tarball, "w:gz", format=tarfile.GNU_FORMAT) as f:
                    cwd = os.getcwd()
                    os.chdir(path_to_upload)
                    for i in os.listdir():
                        f.add(i)
                    os.chdir(cwd)
                path_to_upload = tarball
                explode = True
                mkdir = True

            error = None
            for retry in range(self.retry_count):
                error = None
                try:
                    upload_path_ar = self._get_path(upload_path)
                    if mkdir and not upload_path_ar.exists():
                        upload_path_ar.mkdir()
                    upload_path_ar.deploy_file(
                        path_to_upload,
                        calc_md5=False,
                        calc_sha1=False,
                        calc_sha256=False,
                        explode_archive=explode,
                        explode_archive_atomic=explode,
                    )
                    break
                except Exception as e:
                    error = e
                    print(f"Failed to upload `{original_path_to_upload}` to `{upload_path}`. Error: {e}")
                    time.sleep(self.retry_sleep)

            if error:
                raise error

        self.set_path_properties(upload_path, properties)

    def search_for_child_folder_with_properties(self, path, properties=None, naming_pattern=None,
                                                mandatory_properties=None, quiet=False):
        validate_properties(properties)
        search = [
            {"repo": self.repository},
            {"path": {"$match": path}},
            {"type": "folder"},
        ]
        if properties:
            for k, v in properties.items():
                search.append({f"@{k}": v})
        aql = [
            "items.find",
            {
                "$and": search
            },
            ".include",
            ["path", "name", "repo", "property"],
        ]

        artifacts_list = list()
        error = None
        for retry in range(self.retry_count):
            error = None
            try:
                artifacts_list = self._get_path(self.artifactory_url).aql(*aql)
                break
            except Exception as e:
                error = e
                print(f"Failed to run AQL query`{aql}`. Error: {e}")
                time.sleep(self.retry_sleep)

        if error:
            raise error

        if naming_pattern:
            regex = re.compile(naming_pattern)
            artifacts_list_filtered = list()
            for ar in artifacts_list:
                if regex.match(ar["name"]):
                    artifacts_list_filtered.append(ar)
                elif not quiet:
                    ar_path = ar["path"] + "/" + ar["name"]
                    print(f"Skipping `{ar_path}` since it does not match the naming pattern `{naming_pattern}`")
            artifacts_list = artifacts_list_filtered

        if mandatory_properties:
            artifacts_list_filtered = list()
            for ar in artifacts_list:
                ar_path = ar["path"] + "/" + ar["name"]
                if "properties" in ar:
                    ar_properties = {i["key"]: i["value"] for i in ar["properties"]}
                else:
                    ar_properties = dict()
                add = True
                for mandatory_property in mandatory_properties:
                    if mandatory_property not in ar_properties:
                        if not quiet:
                            print(f"Skipping `{ar_path}` since it's missing the mandatory property "
                                  f"`{mandatory_property}`")
                        add = False
                        break
                    if not ar_properties[mandatory_property].strip():
                        if not quiet:
                            print(f"Skipping `{ar_path}` since the mandatory property `{mandatory_property}` has empty "
                                  f"value")
                        add = False
                        break
                if add:
                    artifacts_list_filtered.append(ar)
            artifacts_list = artifacts_list_filtered

        if not artifacts_list:
            return None
        artifacts_list = sort_list_naturally(artifacts_list, key=lambda x: f"{x['path']}/{x['name']}")
        artifact = artifacts_list[-1]

        if "properties" in artifact:
            artifact["properties"] = {
                i["key"]: [i["value"]] for i in sorted(artifact["properties"], key=lambda x: x["key"])
            }

        return artifact

    def download_file(self, file_path: str, download_dir=None) -> None:
        """
        Downloads the specified file from Artifactory
        :param file_path the full path to the file to download
        :param download_dir the folder path where to download the file
        """
        download_dir = download_dir or os.getcwd()
        file_path = file_path.replace("\\", "/")

        error = None
        for retry in range(self.retry_count):
            error = None
            local_file_name = file_path.split("/")[-1]
            try:
                with tempfile.TemporaryDirectory() as tmp_dir_name:
                    tmp_file_path = os.path.join(tmp_dir_name, local_file_name)

                    self._get_path(file_path).writeto(tmp_file_path, chunk_size=self.chunk_size)

                    local_file_path = os.path.join(download_dir, local_file_name)
                    os.makedirs(download_dir, exist_ok=True)
                    if os.path.exists(local_file_path):
                        os.remove(local_file_path)
                    shutil.move(tmp_file_path, local_file_path)
                break
            except Exception as e:
                error = e
                print(f"Failed while downloading file `{local_file_name}`. Error: {e}")
                time.sleep(self.retry_sleep)

        if error:
            raise error

    def download_folder(self, folder_path: str, download_dir=None, extract=False) -> None:
        """
        Downloads the specified folder from Artifactory as a zip file
        :param folder_path the full path to the folder to download
        """
        current_dir = os.getcwd()
        folder_path = folder_path.replace("\\", "/")
        file_base_name = folder_path.split("/")[-1]
        download_dir = download_dir if download_dir else file_base_name
        file_name = f"{file_base_name}.tar.gz"

        error = None
        for retry in range(self.retry_count):
            error = None
            try:
                with tempfile.TemporaryDirectory() as tmp_dir_name:
                    os.chdir(tmp_dir_name)
                    artifactory_path = self._get_path(folder_path)

                    # Attempt first to download the folder as archive
                    try:
                        artifactory_path.archive(archive_type="tar.gz").writeto(file_name, chunk_size=self.chunk_size)

                        with tarfile.open(file_name) as f:
                            f.extractall()
                        os.remove(file_name)
                    except ArtifactoryException as e:
                        if os.path.exists(file_name):
                            os.remove(file_name)
                        if "exceeds the max allowed folder download size" not in str(e):
                            raise e

                        # Fallback to downloading the folder file by file
                        for child in self.get_children_of_folder(folder_path):
                            if self._get_path(child).is_dir():
                                child_download_dir = f"{tmp_dir_name}/" + child.split("/")[-1]
                                self.download_folder(child, child_download_dir, extract=False)
                            else:
                                self.download_file(child, tmp_dir_name)

                    download_dir_content = os.listdir()
                    if extract and len(download_dir_content) == 1 and download_dir_content[0].endswith(".tar.gz"):
                        inner_tarball = download_dir_content[0]
                        with tarfile.open(inner_tarball) as f:
                            f.extractall()
                        os.remove(inner_tarball)

                    os.chdir(current_dir)
                    if download_dir:
                        os.makedirs(download_dir, exist_ok=True)

                    for i in os.listdir(tmp_dir_name):
                        src = os.path.join(tmp_dir_name, i)
                        dst = os.path.join(download_dir, i)
                        shutil.move(src, dst)
                break
            except Exception as e:
                error = e
                print(f"Failed while downloading `{folder_path}`. Error: {e}")
                time.sleep(self.retry_sleep)
            finally:
                os.chdir(current_dir)

        if error:
            raise error

    def get_children_of_folder(self, path, exclude_folders=False, exclude_files=False):
        if exclude_folders and exclude_files:
            return []

        artifactory_path = self._get_path(path)
        artifactory_path_children = list()

        error = None
        for retry in range(self.retry_count):
            error = None
            try:
                artifactory_path_children = [i for i in artifactory_path.glob("*")]
                break
            except Exception as e:
                error = e
                print(f"Failed to retrieve children of `{path}`. Error: {e}")
                time.sleep(self.retry_sleep)

        if error:
            raise error

        children = []
        for child in artifactory_path_children:
            if exclude_folders or exclude_files:
                is_folder = False

                error = None
                for retry in range(self.retry_count):
                    error = None
                    try:
                        is_folder = child.is_dir()
                        break
                    except Exception as e:
                        error = e
                        print(f"Failed to check if `{child}` is a dir. Error: {e}")
                        time.sleep(self.retry_sleep)

                if error:
                    raise error

                if (is_folder and exclude_folders) or (not is_folder and exclude_files):
                    continue
            children.append(child.path_in_repo.lstrip("/"))
        return sort_list_naturally(children)
