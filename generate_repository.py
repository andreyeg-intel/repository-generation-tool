import os
import argparse
import shutil
import subprocess
import base64
import sys
import platform
import datetime
import json
from distutils.dir_util import copy_tree


def log(*arg, **kwarg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(timestamp, *arg, **kwarg)


def cmd(params):
    try:
        p = subprocess.Popen(params, stdout=subprocess.PIPE)
    except OSError:
        log("ERROR: popen python")
        exit(-1)
    stdout = p.communicate()[0].decode("utf8")
    if p.returncode:
        log("ERROR: " + stdout)
        exit(-1)
    return stdout


def check_prerequisites():
    if not os.environ.get('ARTIFACTORY_USER'):
        log("ERROR: Environment variable 'ARTIFACTORY_USER' is not defined!")
        sys.exit(1)
    if not os.environ.get('ARTIFACTORY_PASS'):
        log("ERROR: Environment variable 'ARTIFACTORY_PASS' is not defined!")
        sys.exit(1)
    if not os.path.exists(os.path.join(os.path.dirname(__file__), "..", "drop_tool", "pdt.py")):
        log("ERROR: Submodule for CDT is not initialized!")
        sys.exit(1)


def create_local_repo(package: dict, distribution_channel: str, publish_dir: str):
    available_distributions = {"yum": yum, "apt": apt}
    product = package['product']
    release = package['release']
    guid = package['guid']
    return available_distributions[distribution_channel](product, release, guid, publish_dir)


def read_meta_data(filename):
    with open(filename) as file:
        return json.load(file)

def package_download(product, release, guid, package_channel, download_dir):

    ARTIFACTORY_USER = os.environ['ARTIFACTORY_USER']
    ARTIFACTORY_PASS = os.environ['ARTIFACTORY_PASS']

    #This is for handlig exceptions in case lack of 'dependency.packages' in meta.yaml
    EMPTY_PROD_ID = 'Empty_product'
    EMPTY_PROD_VER = 'Empty_version'
    EMPTY_POSTFIX = 'Empty_postfix'

    pdt_tool = os.path.join("pdt_tool", "pdt.py")
    if platform.system() in ['Linux', 'Darwin']:
        repositories_path = os.path.join("/work", "repositories")
        temp_dir = os.path.join(repositories_path, "temp")
    else:
        repo_path = os.path.dirname(__file__)
        repositories_path = os.path.join(repo_path, "repositories")
        temp_dir = os.path.join(repositories_path, "temp")
    channel_repo_path = {"yum": "repositories/yum_native",
                         "apt": "repositories/apt_native/pool/main",
                         "webimage": "webimage/"}
    product_skip_list = ["oneapi_installer", "openvino_installer", "pset_build_tools", "software_installer", "wi"]
    if not os.path.exists(repositories_path):
        os.mkdir(repositories_path)
        os.mkdir(temp_dir)
    log("Downloading {channel} channel for package {id}.{version}...".format(channel=package_channel,
                                                                         id=product,
                                                                         version=release))
    stdout = cmd([sys.executable, "-u", pdt_tool,
                                  "-u", ARTIFACTORY_USER,
                                  "-p", ARTIFACTORY_PASS,
                                  "download",
                                  "-p", product,
                                  "-r", release,
                                  "-g", guid,
                                  "-d", download_dir,
                                  "--part", channel_repo_path[package_channel],
                                  "--shallow"])
    log("DONE!")
    stdout = cmd([sys.executable, "-u", pdt_tool,
                                  "-u", ARTIFACTORY_USER,
                                  "-p", ARTIFACTORY_PASS,
                                  "search",
                                  "-p", product,
                                  "-r", release,
                                  "-g", guid,
                                  "-mf", os.path.join(temp_dir, "meta.json")])
    upper_level_meta_data = read_meta_data(os.path.join(temp_dir, "meta.json"))
    try:
        dependency_packages = upper_level_meta_data['resolved properties']['dependency.packages'][0].split(":")
    except:
        dependency_packages = [''.join(f'{EMPTY_PROD_ID}.{EMPTY_PROD_VER}.{EMPTY_POSTFIX}')]
    for dependency_package in dependency_packages:
        dependency_product_id, version, _ = dependency_package.split(".")
        dependency_release_id = ".".join(version.split("_"))
        if dependency_product_id in product_skip_list or package_channel == "webimage":
            continue
        guid_property_name = "dependency.package." + dependency_package
        log("Downloading {channel} channel for package {id}.{version}...".format(channel=package_channel,
                                                                         id=dependency_product_id,
                                                                         version=dependency_release_id))
        stdout = cmd([sys.executable, "-u", pdt_tool,
                                      "-u", ARTIFACTORY_USER,
                                      "-p", ARTIFACTORY_PASS,
                                      "download",
                                      "-p", dependency_product_id,
                                      "-r", dependency_release_id,
                                      "-g", upper_level_meta_data['resolved properties'][guid_property_name][0],
                                      "-d", download_dir,
                                      "--part", channel_repo_path[package_channel],
                                      "--shallow"])
        log("DONE!")
    shutil.rmtree(temp_dir)


def yum(product, release, guid, publish_dir):
    channel_dir = "yum"
    source_dir = os.path.join(publish_dir, "SOURCES")
    yum_repo_gen_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "channels", "yum", "create_repo.sh")

    if os.path.exists(publish_dir):
        shutil.rmtree(publish_dir)
    os.makedirs(publish_dir)
    
    package_download(product, release, guid, channel_dir, source_dir)

    shutil.rmtree(os.path.join(source_dir, "repositories", "yum_native", "repodata"))
    
    try:
        output = subprocess.check_output("createrepo --help", shell=True)
    except subprocess.CalledProcessError as e:
        print(e)
        print("createrepo tool is required for generating YUM repository.")
        exit(1)

    log("Generating YUM repository for {product}...".format(product=product))
    output = ''
    try:
        output = subprocess.check_output(["/bin/bash", yum_repo_gen_script_path, os.path.join(source_dir, "repositories", "yum_native"),
                                        publish_dir], stderr=subprocess.STDOUT).decode("utf-8", errors='ignore')

        shutil.rmtree(source_dir)
        log("Generating YUM repository...Done")
    except subprocess.CalledProcessError as e:
        print(e)
        output = e.output.decode('utf-8', errors='ignore')
        shutil.rmtree(source_dir)
    except Exception as e:
        print(e)
    print(output)

    print("Registering YUM repository on machine")
    local_repo_filename = product + ".repo"
    repo_file_path = os.path.join(os.getcwd(), local_repo_filename)
    repo_file_content = ''.join(("[{id}]\n".format(id=product),
                                 "name=Intel(R) oneAPI repository\n",
                                 "baseurl=file:{repo_dir}\n".format(repo_dir=publish_dir),
                                 "enabled=1\n",
                                 "gpgcheck=0\n",
                                 "repo_gpgcheck=0\n"))
    with open(repo_file_path, "w") as file:
        file.write(repo_file_content)
    shutil.copyfile(repo_file_path, "/etc/yum.repos.d/" + local_repo_filename)
    os.remove(repo_file_path)
    print("Registering YUM repository on machine...Done")
    return True


def apt(product, release, guid, publish_dir):
    channel_dir = "apt"
    source_dir = os.path.join(publish_dir, "SOURCES")
    apt_repo_gen_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "channels", "apt", "create_repo.sh")
    
    if os.path.exists(publish_dir):
        shutil.rmtree(publish_dir)
    os.makedirs(publish_dir)

    package_download(product, release, guid, channel_dir, source_dir)

    print("Generating APT repository...")
    output = ''
    try:
        output = subprocess.check_output(["/bin/bash", apt_repo_gen_script_path,
                                                        os.path.join(source_dir, "repositories", "apt_native", "pool", "main"),
                                                        publish_dir], stderr=subprocess.STDOUT).decode("utf-8", errors='ignore')
        shutil.rmtree(source_dir)
        print("Generating APT repository...Done")
    except subprocess.CalledProcessError as e:
        print(e)
        output = e.output.decode('utf-8', errors='ignore')
        shutil.rmtree(source_dir)
    except Exception as e:
        print(e)
    print(output)

    print("Registering APT repository on machine...")
    local_repo_filename = product + ".list"
    repo_file_path = os.path.join(os.getcwd(), local_repo_filename)
    repo_file_content = 'deb [trusted=yes] file://{path} all main'.format(path=publish_dir)
    with open(repo_file_path, "w") as file:
        file.write(repo_file_content)
    os.makedirs("/etc/apt/sources.list.d", exist_ok=True)
    shutil.copyfile(repo_file_path, "/etc/apt/sources.list.d/" + local_repo_filename)
    os.remove(repo_file_path)
    subprocess.check_output("apt update", shell=True)
    print("Registering APT repository on machine...Done")
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--product_id", type=str, required=True)
    parser.add_argument("--release_id", type=str, required=True)
    parser.add_argument("--package_guid", type=str, required=True)
    parser.add_argument("--distribution", required=True, choices=("apt","yum"))
    parser.add_argument("--publish_dir", type=str, required=True)

    arguments = parser.parse_args()

    distribution: str = arguments.distribution
    publish_dir: str = arguments.publish_dir

    package = dict()
    package['product'] = arguments.product_id
    package['release'] = arguments.release_id
    package['guid'] = arguments.package_guid


    check_prerequisites()

    create_local_repo(package, distribution, publish_dir)
    exit(0)
