import json
import os.path
import uuid
from datetime import datetime

import yaml

from helpers.artifactory import *
from helpers.bom import *

urllib3.disable_warnings()

repo_dir = os.path.abspath(os.path.dirname(__file__))
execution_dir = os.getcwd()
timestamp_format = r"%Y%m%d%H%M%S"
execution_time = datetime.now().strftime(timestamp_format)


def parse_args():
    ######################################################################################################
    # Define a parser that contains the common options for different actions
    ######################################################################################################
    common_options = argparse.ArgumentParser(add_help=False)
    common_options.add_argument('--product', '-p',
                                metavar='PRODUCT',
                                required=True,
                                help="Product abbreviation to access its drops.")
    common_options.add_argument('--release', '-r',
                                metavar='RELEASE',
                                required=True,
                                help="Release name/ID to access its drops.")

    ######################################################################################################
    # Define the actual parser for this entire script
    ######################################################################################################
    parser = argparse.ArgumentParser(description="Tool to assist with dropping and fetching components")
    parser.add_argument('--username', "-u",
                        metavar='USER',
                        required=True,
                        help='Username to access Artifactory drop repository')
    parser.add_argument('--password', "-p",
                        metavar='PASSWORD',
                        required=False)
    parser.add_argument('--password-file', "-pf",
                        metavar='PASSWORD_FILE',
                        required=False,
                        help="File containing password for the specified user")
    parser.add_argument("--verbose", "-v",
                        action="store_true",
                        help="Print debug messages")

    subparsers = parser.add_subparsers(dest='action', help='action to perform')
    subparsers.required = True

    ######################################################################################################
    # Define the parser to handle dropping
    ######################################################################################################
    subparser_drop = subparsers.add_parser('drop',
                                           parents=[common_options],
                                           help='Drops the specified components to the selected project')
    subparser_drop.add_argument('--component', '-c',
                                metavar='COMPONENT',
                                required=True,
                                help="Component name to drop.")
    subparser_drop.add_argument('--component-dir', '-cd',
                                metavar='COMPONENT_DIR',
                                required=False,
                                help="Path to the folder containing the fileset to drop. Defaults to a sub dir "
                                     "with the same name of the component in the execution dir.")
    subparser_drop.add_argument('--reports-dir', '-rd',
                                metavar='REPORTS_DIR',
                                required=False,
                                help="Path to the folder containing the reports of the component being dropped.")
    subparser_drop.add_argument('--meta-file', '-mf',
                                metavar='META_FILE',
                                required=False,
                                help="Path to the meta file (json/yaml) format to be uploaded together with the "
                                     "component's fileset.")
    subparser_drop.add_argument('--result-file', '-rf',
                                metavar='RESULT_FILE',
                                required=False,
                                help="Path to where to place the json meta file generated after the drop.")
    subparser_drop.add_argument('--boms', '-b',
                                nargs="*",
                                metavar='BOM',
                                required=False,
                                help="Path to the bom file or bom folder of the component being dropped. If no bom file"
                                     " is provided, it will be auto-generated.")
    subparser_drop.add_argument("--property", "-pr",
                                nargs="*",
                                metavar="KEY=VALUE",
                                required=False,
                                help="Property KEY=VALUE pair to attach as a property to the drops.")
    subparser_drop.add_argument("--timestamp", "-t",
                                metavar="TIMESTAMP",
                                required=False,
                                default=execution_time,
                                help="Drop timestamp to use while dropping. Default to current timestamp. "
                                     "Use format yyyymmddHHMMSS")
    subparser_drop.add_argument("--no-compress",
                                action="store_true",
                                help="Do not compress the component fileset when dropping. By default, the component's "
                                     "fileset will be compressed into a GNU tarball before dropping them.")

    ######################################################################################################
    # Define the parser to handle searching for a drop location
    ######################################################################################################
    parser_search = argparse.ArgumentParser(add_help=False)
    parser_search.add_argument('--component', '-c',
                               metavar='COMPONENT',
                               required=True)
    parser_search.add_argument('--guid', '-g',
                               metavar='DROP_GUID',
                               required=False,
                               help="Drop GUID property to search for.")
    parser_search.add_argument("--property", "-pr",
                               nargs="*",
                               required=False,
                               metavar="KEY=VALUE",
                               help="Property KEY=VALUE pair to use to locate a drop location")
    parser_search.add_argument('--search-meta-file', '-mf',
                               metavar='SEARCH_META_FILE',
                               required=False,
                               help="Path to the where to place the json meta file related to the found drop.")
    subparsers.add_parser('search',
                          parents=[common_options, parser_search],
                          help='Search for a drop location based on some criteria.')

    ######################################################################################################
    # Define the parser to handle downloading drop locations
    ######################################################################################################
    subparser_download = subparsers.add_parser('download',
                                               parents=[common_options, parser_search],
                                               help='Search and download a drop location based on some criteria')
    subparser_download.add_argument("--extract", "-x",
                                    action="store_true",
                                    help="Assuming the downloaded component's fileset were compressed during the drop, "
                                         "this option will extract the compressed GNU tarball.")
    subparser_download.add_argument('--download-dir', '-d',
                                    metavar='DOWNLOAD_DIR',
                                    required=False,
                                    default=os.getcwd(),
                                    help="Path to the folder where to download the component's drop fileset. Defaults "
                                         "to current dir.")

    _args = parser.parse_args()

    # Evaluate the password option
    if _args.password and _args.password_file:
        parser.error("Options `--password` and `--password-file` cannot be provided at the same time.")
    elif not _args.password and not _args.password_file:
        parser.error("Option `--password` or `--password-file` is required.")
    elif _args.password_file:
        _args.password_file = os.path.expanduser(_args.password_file)
        if not os.path.exists(_args.password_file):
            parser.error(f"Password file provided `{_args.password_file} does not exist.")
        with open(_args.password_file, "r") as file:
            _args.password = file.read().strip()

    # Evaluate the properties field
    if hasattr(_args, "property") and _args.property:
        properties = dict()
        for i in _args.property:
            if "=" not in i:
                parser.error(f"Invalid property `{i}`. Property should be of format `KEY=VALUE`.")
            key, value = i.split("=", 1)
            properties[key] = value
        validate_properties(properties)
        _args.property = properties

    if _args.action == "drop":
        component_dir = _args.component_dir
        if not component_dir:
            _args.component_dir = os.path.join(execution_dir, _args.component)
        elif not os.path.exists(component_dir) or not os.path.isdir(component_dir):
            parser.error(f"Component dir provided `{component_dir}` does not exist or is not a dir.")

        reports_dir = _args.reports_dir
        if reports_dir:
            if not os.path.exists(reports_dir) or not os.path.isdir(reports_dir):
                parser.error(f"Reports dir provided `{reports_dir}` does not exist or is not a dir.")

        meta_file = _args.meta_file
        if meta_file:
            valid_formats = ["json", "yaml", "yml"]
            if not os.path.exists(meta_file) or not os.path.isfile(meta_file):
                parser.error(f"Meta file provided `{meta_file}` does not exist or is not a file.")
            elif not any(meta_file.lower().endswith(i) for i in valid_formats):
                parser.error(f"Meta file provided `{meta_file}` has an invalid file extension.")

        if _args.boms:
            resolved_boms = list()
            for b in _args.boms:
                if not os.path.exists(b):
                    parser.error(f"Bom path provided `{b}` does not exist.")
                if os.path.isfile(b):
                    resolved_boms.append(b)
                else:
                    resolved_boms += [os.path.join(b, i) for i in os.listdir(b) if i.endswith(".txt")]
            _args.boms = resolved_boms

    return _args


def get_component_drop_base_location(product: str, release: str, component: str):
    return f"products/{product}/{release}/drops/{component}"


def do_drop(api: ArtifactoryHelper, product: str, release: str, component: str, component_dir: str,
            reports_dir: str = None, meta_file: str = None, boms: list = None,
            properties: dict = None,
            timestamp: str = None, compress=True, result_file=None):
    def print_summary():
        meta = {
            "product": product,
            "release": release,
            "component": component,
            "component os": component_os,
            "component dir": component_dir,
            "component fileset": component_fileset_to_drop,
            "drop timestamp": timestamp,
            "execution timestamp": execution_time,
            "compressed fileset": compress,
        }

        if reports_dir:
            meta["reports folder"] = reports_dir
        if meta_file:
            meta["meta file"] = meta_file
        if boms:
            meta["boms"] = boms
        if properties:
            meta["properties"] = properties

        meta["artifactory path"] = base_artifactory_path
        print(json.dumps(meta, indent=4))

        if result_file:
            do_search(
                api=api,
                product=product,
                release=release,
                component=component,
                guid=drop_guid,
                timestamp=timestamp,
                search_meta_file=result_file,
            )

    def read_meta_file():
        content = dict()
        if meta_file and os.path.exists(meta_file) and os.path.isfile(meta_file):
            extension = meta_file.split(".")[-1].lower()
            with open(meta_file) as f:
                if extension == "json":
                    content = json.load(f)
                else:
                    content = yaml.safe_load(f)
        return content

    def update_properties():
        if meta_file and os.path.exists(meta_file) and os.path.isfile(meta_file):
            content = read_meta_file()
            if isinstance(content, dict):
                for key, val in content.items():
                    if isinstance(val, dict):
                        continue
                    if isinstance(val, list):
                        if any(isinstance(i, dict) for i in val):
                            continue
                    properties[f"meta.{key}"] = val

        properties.update(auto_properties)

    def patch_meta_file():
        content = read_meta_file()
        if isinstance(content, list):
            content = {"meta": content}
        content.update(**auto_properties)
        temp_meta_file = os.path.join(repo_dir, "meta.yaml")
        with open(temp_meta_file, "w") as f:
            yaml.dump(content, f)

    # Validate and process the args
    if not product:
        raise Exception(f"Invalid product key provided `{product}`.")
    if not release:
        raise Exception(f"Invalid release key provided `{release}`.")
    if not component:
        raise Exception(f"Invalid component name provided `{component}`.")
    component_dir = component_dir if component_dir is not None else os.path.join(execution_dir, component)
    component_dir = os.path.abspath(component_dir)
    if not os.path.exists(component_dir):
        raise Exception(f"Component dir `{component_dir}` does not exist.")
    component_fileset_to_drop = component_dir
    if component.startswith("l_"):
        component_os = "Linux"
    elif component.startswith("w_"):
        component_os = "Windows"
    elif component.startswith("m_"):
        component_os = "Mac"
    elif component.startswith("x_") or component.startswith("crossplatf_"):
        component_os = "Cross-OS"
    else:
        raise Exception(f"Component name provided does not match any OS convention `{component}`.")
    generate_bom = not boms
    boms = boms if boms else [os.path.join(execution_dir, "boms", f"{component}.txt")]
    boms = sorted([os.path.abspath(i) for i in boms])
    properties = properties or dict()
    drop_guid = str(uuid.uuid4())
    timestamp = timestamp or execution_time
    # Validate the timestamp format
    datetime.strptime(timestamp, timestamp_format)
    auto_properties = {
        "auto.drop_execution_time": execution_time,
        "auto.timestamp": timestamp,
        "auto.guid": drop_guid,
        "retention.days": 60,
    }

    update_properties()
    validate_properties(properties)
    patch_meta_file()

    reports_dir = reports_dir if reports_dir is not None else os.path.join(execution_dir, "reports", component)
    reports_dir = os.path.abspath(reports_dir)

    try:
        # Generate the BOM if needed
        if generate_bom:
            generate_bom_for_path(component_dir, boms[0])

        # Compress the component's fileset if needed
        if compress:
            compressed_file_dir = os.path.join(execution_dir, f"{product}_{release}")
            compressed_file = os.path.join(compressed_file_dir, f"{component}.tar.gz")
            if os.path.exists(compressed_file):
                os.remove(compressed_file)
            os.makedirs(compressed_file_dir, exist_ok=True)
            current_dir = os.getcwd()
            try:
                os.chdir(component_dir)
                with tarfile.open(compressed_file, "w:gz", format=tarfile.GNU_FORMAT) as f:
                    for i in os.listdir(os.getcwd()):
                        f.add(i)
            finally:
                os.chdir(current_dir)
            component_fileset_to_drop = compressed_file

        # Define the relative paths to upload
        paths = {
            "boms": boms,
            "meta": os.path.join(repo_dir, "meta.yaml"),
            "reports": reports_dir,
            "fileset": component_fileset_to_drop,
        }

        # Delete the base location in Artifactory
        base_artifactory_path = get_component_drop_base_location(product, release, component) + f"/{timestamp}"
        api.delete_path(base_artifactory_path)

        try:
            # Upload the resources to Artifactory
            for relative_dir, source in paths.items():
                if not source:
                    continue
                print(relative_dir, source)
                source = source if isinstance(source, list) else [source]
                for s in source:
                    if not os.path.exists(s):
                        continue
                    if os.path.isdir(s):
                        api.upload(s, f"{base_artifactory_path}/{relative_dir}")
                    else:
                        source_base_name = os.path.basename(s)
                        api.upload(s, f"{base_artifactory_path}/{relative_dir}/{source_base_name}")

            # Set the properties
            api.set_path_properties(base_artifactory_path, properties)
        except:
            # Do not leave non-complete drops.
            api.delete_path(base_artifactory_path)
            raise

        print_summary()
    finally:
        # Delete the bom file and it's folder if it was automatically generated
        if generate_bom and boms and os.path.exists(boms[0]):
            os.remove(boms[0])
            bom_dir = os.path.dirname(boms[0])
            if not os.listdir(bom_dir):
                shutil.rmtree(bom_dir)

        # Delete the compressed file if needed
        if compress and component_fileset_to_drop.endswith(".tar.gz"):
            os.remove(component_fileset_to_drop)

        if os.path.exists(os.path.join(repo_dir, "meta.yaml")):
            os.remove(os.path.join(repo_dir, "meta.yaml"))


def do_search(api: ArtifactoryHelper, product: str, release: str, component: str,
              guid: str = None, timestamp: str = None, properties: dict = None, search_meta_file: str = None):
    properties = properties or dict()
    if guid:
        properties["auto.guid"] = guid
    if timestamp:
        properties["auto.timestamp"] = timestamp
    base_artifactory_path = get_component_drop_base_location(product, release, component)

    mandatory_properties = ["auto.guid", "auto.timestamp", "auto.drop_execution_time"]
    path = api.search_for_child_folder_with_properties(base_artifactory_path, properties,
                                                       naming_pattern=f"^\\d{{{len(execution_time)}}}$",
                                                       mandatory_properties=mandatory_properties)

    if not path:
        msg = f"No component drop found that matches the search criteria"
        if properties:
            msg += f": `{properties}`"
        raise Exception(msg)

    meta = {
        "product": product,
        "release": release,
        "component": component,
        "path": f"{path['path']}/{path['name']}",
        "search properties": properties,
        "resolved properties": path["properties"],
    }
    if search_meta_file:
        search_meta_file_dir = os.path.dirname(search_meta_file)
        if search_meta_file_dir:
            os.makedirs(search_meta_file_dir, exist_ok=True)
        with open(search_meta_file, "w") as f:
            json.dump(meta, f, indent=4)
    return meta


def do_download(api: ArtifactoryHelper, product: str, release: str, component: str,
                guid: str = None, timestamp: str = None, properties: dict = None,
                download_dir=None, extract=True, search_meta_file: str = None):
    download_dir = download_dir or os.getcwd()
    meta = do_search(
        api=api,
        product=product,
        release=release,
        component=component,
        guid=guid,
        timestamp=timestamp,
        properties=properties,
        search_meta_file=search_meta_file,
    )
    print(json.dumps(meta, indent=4))
    api.download_folder(
        meta["path"] + "/fileset",
        download_dir=download_dir,
        extract=extract,
    )
    api.download_folder(
        meta["path"] + "/boms",
        download_dir=download_dir + "/boms"
    )
    return meta


def main():
    args = parse_args()
    api = ArtifactoryHelper(args.username, args.password, verbose=args.verbose)
    if args.action == "drop":
        do_drop(
            api=api,
            product=args.product,
            release=args.release,
            component=args.component,
            component_dir=args.component_dir,
            reports_dir=args.reports_dir,
            meta_file=args.meta_file,
            boms=args.boms,
            properties=args.property,
            timestamp=args.timestamp,
            compress=not args.no_compress,
            result_file=args.result_file,
        )
    elif args.action == "search":
        meta = do_search(
            api=api,
            product=args.product,
            release=args.release,
            component=args.component,
            guid=args.guid,
            properties=args.property,
            search_meta_file=args.search_meta_file,
        )
        print(json.dumps(meta, indent=4))
    elif args.action == "download":
        do_download(
            api=api,
            product=args.product,
            release=args.release,
            component=args.component,
            guid=args.guid,
            properties=args.property,
            download_dir=args.download_dir,
            extract=args.extract,
            search_meta_file=args.search_meta_file,
        )


if __name__ == "__main__":
    main()
