import pytest

from helpers.artifactory import *

artifactory_url = "https://ubit-artifactory-or.intel.com/artifactory"
artifactory_repository = "satgoneapi-or-local"
product = "product_name"
release = "release_name"
component_name = "component_name"
ar = ArtifactoryHelper("username", "password", artifactory_url, artifactory_repository)
component_drop_relative_path = f"products/{product}/{release}/drops/{component_name}"
component_storage_url = f"{artifactory_url}/api/storage/{artifactory_repository}/{component_drop_relative_path}"
component_full_url = f"{artifactory_url}/{artifactory_repository}/{component_drop_relative_path}"
search_url = f"{artifactory_url}/api/search/pattern?pattern={artifactory_repository}"


def test_validate_properties_valid():
    properties = {"build": "9"}
    validate_properties(properties)
    assert True


def test_validate_properties_invalid_char():
    for i in forbidden_key_chars:
        properties = {i: "value"}
        with pytest.raises(Exception) as info:
            validate_properties(properties)
            assert str(info.value) == f"Invalid characters found in property key `{i}`."


def test_sort_list_naturally_string():
    list_to_sort = ["b", "a"]
    result = sort_list_naturally(list_to_sort, False)
    assert result == ['a', 'b']


def test_sort_list_naturally_number():
    list_to_sort = [12, 2]
    result = sort_list_naturally(list_to_sort, False)
    assert result == [2, 12]


def test_sort_list_naturally_string_with_numbers():
    list_to_sort = ["a_123", "a_2"]
    files_found = sort_list_naturally(list_to_sort, False)
    assert files_found == ['a_2', 'a_123']


def test_sort_list_naturally_string_numbers_slash():
    list_to_sort = ["a_123/a_2", "a_2/a_123", "a_2/a_100"]
    files_found = sort_list_naturally(list_to_sort, False)
    assert files_found == ['a_2/a_100', 'a_2/a_123', 'a_123/a_2']


def test_sort_list_naturally_string_reverse():
    list_to_sort = ["a_2/a_100", "a_123/a_2", "a_2/a_123", ]
    files_found = sort_list_naturally(list_to_sort, True)
    assert files_found == ['a_123/a_2', 'a_2/a_123', 'a_2/a_100']
