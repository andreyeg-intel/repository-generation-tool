import json
from datetime import datetime

from helpers.artifactory import *
from helpers.bom import *

urllib3.disable_warnings()

repo_dir = os.path.abspath(os.path.dirname(__file__))
execution_dir = os.getcwd()
execution_time = datetime.now().strftime(r"%Y%m%d%H%M%S")


def parse_args():
    current_platform = platform.system().lower()
    if "linux" in current_platform:
        package_os_selection = "linux"
    elif "darwin" in current_platform:
        package_os_selection = "mac"
    elif "windows" in current_platform:
        package_os_selection = "windows"
    else:
        package_os_selection = "cross"

    ######################################################################################################
    # Define a parser that contains the common options for different actions
    ######################################################################################################
    common_options = argparse.ArgumentParser(add_help=False)
    common_options.add_argument('--product', '-p',
                                metavar='PRODUCT',
                                required=True,
                                help="Product abbreviation to access its packages.")
    common_options.add_argument('--release', '-r',
                                metavar='RELEASE',
                                required=True,
                                help="Release name/ID to access its packages.")
    common_options.add_argument('--package-os', "--os",
                                metavar='PACKAGE_OS',
                                choices=["windows", "win", "w", "linux", "lin", "l", "mac", "m", "cross", "c", "x"],
                                default=package_os_selection,
                                type=str.lower,
                                help=f'Package OS to access. Defaults to `{package_os_selection}`.')

    ######################################################################################################
    # Define the actual parser for this entire script
    ######################################################################################################
    parser = argparse.ArgumentParser(description="Tool to assist with fetching packages")
    parser.add_argument('--username', "-u",
                        metavar='USER',
                        required=True,
                        help='Username to access Artifactory package repository')
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
    # Define the parser to handle searching for a package location
    ######################################################################################################
    parser_search = argparse.ArgumentParser(add_help=False)
    parser_search.add_argument("--property", "-pr",
                               nargs="*",
                               required=False,
                               metavar="KEY=VALUE",
                               help="Property KEY=VALUE pair to use to locate a package location")
    parser_search.add_argument('--guid', '-g',
                               metavar='PACKAGE_GUID',
                               required=False,
                               help="Package GUID property to search for.")
    parser_search.add_argument('--search-meta-file', '-mf',
                               metavar='SEARCH_META_FILE',
                               required=False,
                               help="Path to the where to place the json meta file related to the found package.")
    subparsers.add_parser('search',
                          parents=[common_options, parser_search],
                          help='Search for a package location based on some criteria.')

    ######################################################################################################
    # Define the parser to handle downloading package locations
    ######################################################################################################
    subparser_download = subparsers.add_parser('download',
                                               parents=[common_options, parser_search],
                                               help='Search and download a package location based on some criteria')
    subparser_download.add_argument('--part',
                                    metavar='PART',
                                    required=False,
                                    help="Download only specific dir of the package.")
    subparser_download.add_argument('--shallow',
                                    action='store_true',
                                    required=False,
                                    default=False,
                                    help="Do not download subdirectory contents.")
    subparser_download.add_argument('--download-dir', '-d',
                                    metavar='DOWNLOAD_DIR',
                                    required=False,
                                    default=os.getcwd(),
                                    help="Path to the folder where to download the package. Defaults "
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

    # Evaluate the package OS selection
    if _args.package_os:
        _args.package_os = resolve_package_os_abbreviation(_args.package_os)

    return _args


def resolve_package_os_abbreviation(package_os=platform.system()):
    package_os = package_os if package_os else platform.system()
    if package_os.startswith("l"):
        return "l"
    elif package_os.startswith("w"):
        return "w"
    elif package_os.startswith("m"):
        return "m"
    elif package_os.startswith("c") or package_os.startswith("x"):
        return "cross"
    return package_os


def get_package_base_location(product: str, release: str):
    return f"products/{product}/{release}/packages"


def do_search(api: ArtifactoryHelper, product: str, release: str, package_os: str = None, guid: str = None,
              properties: dict = None, search_meta_file: str = None):
    package_os = resolve_package_os_abbreviation(package_os)
    properties = properties or dict()
    if guid:
        properties["auto.guid"] = guid
    base_artifactory_path = get_package_base_location(product, release)
    mandatory_properties = ["auto.guid", "auto.package_id"]
    path = api.search_for_child_folder_with_properties(base_artifactory_path, properties,
                                                       naming_pattern=f"^{package_os}_.*$",
                                                       mandatory_properties=mandatory_properties,
                                                       quiet=True)

    if not path:
        msg = f"No package found that matches the search criteria"
        if properties:
            msg += f": `{properties}`"
        raise Exception(msg)

    meta = {
        "product": product,
        "release": release,
        "package_os": package_os,
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


def do_download(api: ArtifactoryHelper, product: str, release: str, guid: str = None, properties: dict = None,
                package_os: str = None, download_dir: str = None, shallow: bool = False, part: str = None,
                search_meta_file: str = None):
    download_dir = download_dir or os.getcwd()
    meta = do_search(
        api=api,
        product=product,
        release=release,
        guid=guid,
        properties=properties,
        package_os=package_os,
        search_meta_file=search_meta_file,
    )
    print(json.dumps(meta, indent=4))

    path = meta["path"] if not part else meta["path"] + "/" + part
    download_dir = download_dir if not part else download_dir + "/" + part
    if shallow:
        for fn in api.get_children_of_folder(path, exclude_folders=True):
            api.download_file(fn, download_dir)
        for fn in api.get_children_of_folder(path, exclude_files=True):
            fn2 = os.path.join(download_dir, os.path.basename(fn))
            if not os.path.exists(fn2):
                os.makedirs(fn2)
    else:
        api.download_folder(path, download_dir=download_dir)
    return meta


def main():
    args = parse_args()
    api = ArtifactoryHelper(args.username, args.password, verbose=args.verbose)
    if args.action == "search":
        meta = do_search(
            api=api,
            product=args.product,
            release=args.release,
            guid=args.guid,
            properties=args.property,
            package_os=args.package_os,
            search_meta_file=args.search_meta_file,
        )
        print(json.dumps(meta, indent=4))
    if args.action == "download":
        do_download(
            api=api,
            product=args.product,
            release=args.release,
            guid=args.guid,
            properties=args.property,
            package_os=args.package_os,
            download_dir=args.download_dir,
            shallow=args.shallow,
            part=args.part,
            search_meta_file=args.search_meta_file,
        )


if __name__ == "__main__":
    main()
