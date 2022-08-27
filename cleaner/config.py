from os.path import dirname, realpath
from pathlib import Path

from dynaconf import Dynaconf
from loguru import logger  # noqa: F401

current_directory = Path(dirname(realpath(__file__)))


settings = Dynaconf(
    envvar_prefix="DYNACONF",
    settings_files=[current_directory.joinpath(file) for file in ("settings.toml", ".secrets.toml")],
)
