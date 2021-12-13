import os
import pkgutil
from importlib import import_module
from types import ModuleType
from typing import Sequence, Union

from .asset import AssetsDefinition
from .foreign_asset import ForeignAsset


def gather_assets_in_package(
    package_module: ModuleType,
) -> Sequence[Union[AssetsDefinition, ForeignAsset]]:
    # TODO: raise helpful error if package dir is not on path

    results = []

    for importer, modname, is_pkg in pkgutil.walk_packages(
        [os.path.dirname(package_module.__file__)]
    ):
        if not is_pkg:
            module = import_module(f"{package_module.__name__}.{modname}")
            for attr in dir(module):
                value = getattr(module, attr)
                if isinstance(value, AssetsDefinition) or isinstance(value, ForeignAsset):
                    results.append(value)

    return results
