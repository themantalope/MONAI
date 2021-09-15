# Copyright 2020 - 2021 MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
from typing import Dict, List, Optional, Sequence, Union, overload

from monai.utils import ensure_tuple


@overload
def _compute_path(base_dir: str, element: str, check_path: bool = False) -> str:
    ...


@overload
def _compute_path(base_dir: str, element: List[str], check_path: bool = False) -> List[str]:
    ...


def _compute_path(base_dir, element, check_path=False):
    """
    Args:
        base_dir: the base directory of the dataset.
        element: file path(s) to append to directory.
        check_path: if `True`, only compute when the result is an existing path.

    Raises:
        TypeError: When ``element`` contains a non ``str``.
        TypeError: When ``element`` type is not in ``Union[list, str]``.

    """

    def _join_path(base_dir: str, item: str):
        result = os.path.normpath(os.path.join(base_dir, item))
        if check_path and not os.path.exists(result):
            # if not an existing path, don't join with base dir
            return item
        return result

    if isinstance(element, str):
        return _join_path(base_dir, element)
    if isinstance(element, list):
        for e in element:
            if not isinstance(e, str):
                return element
        return [_join_path(base_dir, e) for e in element]
    return element


def _append_paths(base_dir: str, is_segmentation: bool, items: List[Dict]) -> List[Dict]:
    """
    Args:
        base_dir: the base directory of the dataset.
        is_segmentation: whether the datalist is for segmentation task.
        items: list of data items, each of which is a dict keyed by element names.

    Raises:
        TypeError: When ``items`` contains a non ``dict``.

    """
    for item in items:
        if not isinstance(item, dict):
            raise TypeError(f"Every item in items must be a dict but got {type(item).__name__}.")
        for k, v in item.items():
            if k == "image" or is_segmentation and k == "label":
                item[k] = _compute_path(base_dir, v, check_path=False)
            else:
                # for other items, auto detect whether it's a valid path
                item[k] = _compute_path(base_dir, v, check_path=True)
    return items


def load_decathlon_datalist(
    data_list_file_path: str,
    is_segmentation: bool = True,
    data_list_key: str = "training",
    base_dir: Optional[str] = None,
) -> List[Dict]:
    """Load image/label paths of decathlon challenge from JSON file

    Json file is similar to what you get from http://medicaldecathlon.com/
    Those dataset.json files

    Args:
        data_list_file_path: the path to the json file of datalist.
        is_segmentation: whether the datalist is for segmentation task, default is True.
        data_list_key: the key to get a list of dictionary to be used, default is "training".
        base_dir: the base directory of the dataset, if None, use the datalist directory.

    Raises:
        ValueError: When ``data_list_file_path`` does not point to a file.
        ValueError: When ``data_list_key`` is not specified in the data list file.

    Returns a list of data items, each of which is a dict keyed by element names, for example:

    .. code-block::

        [
            {'image': '/workspace/data/chest_19.nii.gz',  'label': 0},
            {'image': '/workspace/data/chest_31.nii.gz',  'label': 1}
        ]

    """
    if not os.path.isfile(data_list_file_path):
        raise ValueError(f"Data list file {data_list_file_path} does not exist.")
    with open(data_list_file_path) as json_file:
        json_data = json.load(json_file)
    if data_list_key not in json_data:
        raise ValueError(f'Data list {data_list_key} not specified in "{data_list_file_path}".')
    expected_data = json_data[data_list_key]
    if data_list_key == "test":
        expected_data = [{"image": i} for i in expected_data]

    if base_dir is None:
        base_dir = os.path.dirname(data_list_file_path)

    return _append_paths(base_dir, is_segmentation, expected_data)


def load_decathlon_properties(
    data_property_file_path: str,
    property_keys: Union[Sequence[str], str],
) -> Dict:
    """Load the properties from the JSON file contains data property with specified `property_keys`.

    Args:
        data_property_file_path: the path to the JSON file of data properties.
        property_keys: expected keys to load from the JSON file, for example, we have these keys
            in the decathlon challenge:
            `name`, `description`, `reference`, `licence`, `tensorImageSize`,
            `modality`, `labels`, `numTraining`, `numTest`, etc.

    """
    if not os.path.isfile(data_property_file_path):
        raise ValueError(f"Data property file {data_property_file_path} does not exist.")
    with open(data_property_file_path) as json_file:
        json_data = json.load(json_file)

    properties = {}
    for key in ensure_tuple(property_keys):
        if key not in json_data:
            raise KeyError(f"key {key} is not in the data property file.")
        properties[key] = json_data[key]
    return properties
