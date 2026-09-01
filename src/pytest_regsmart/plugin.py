from __future__ import annotations
 
import pytest
from _pytest.config import Config
from _pytest.config.argparsing import Parser
 
from . import options
from .config import PluginConfig
from .runner import PluginRunner
 
 
def pytest_addoption(parser: Parser) -> None:
    options.add_options(parser)
    options.add_ini_options(parser)
 
 
@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    options.validate_options(config)
 
    plugin_config = PluginConfig.from_pytest_config(config)
    runner = PluginRunner(config, plugin_config)
    config.pluginmanager.register(runner)
