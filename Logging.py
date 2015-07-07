"""SConsider.Logging.

Provides logging initialization and a regular expression based filter.

"""
# vim: set et ai ts=4 sw=4:
# -------------------------------------------------------------------------
# Copyright (c) 2014, Peter Sommerlad and IFS Institute for Software
# at HSR Rapperswil, Switzerland
# All rights reserved.
#
# This library/application is free software; you can redistribute and/or
# modify it under the terms of the license that is included with this
# library/application in the file license.txt.
# -------------------------------------------------------------------------

import os
import logging
import yaml
import re

"""Work around missing dictConfig in python < 2.7
http://www.calazan.com/how-to-configure-the-logging-module-using-dictionaries-in-python-2-6/
"""
try:
    from logging.config import dictConfig as from_dictConfig
    from logging import captureWarnings
except:
    from dictconfig import dictConfig as from_dictConfig

    def captureWarnings(arg):
        pass


def setup_logging(
        default_path='logging.yaml',
        default_level=logging.WARNING,
        env_key='LOG_CFG',
        capture_warnings=True):
    """Setup logging configuration

    Based on http://victorlin.me/posts/2012/08/good-logging-practice-in-python/
    """
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = yaml.load(f.read())
        from_dictConfig(config)
    else:
        logging.basicConfig(level=default_level)
    captureWarnings(capture_warnings)


class RegexFilter(logging.Filter):

    def __init__(self, pattern=None, flags=0):
        self.compiled = None
        if pattern:
            self.compiled = re.compile(pattern, flags)

    def filter(self, record):
        if not self.compiled:
            return True
        return not self.compiled.match(record.getMessage())
