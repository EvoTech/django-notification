from __future__ import absolute_import, unicode_literals
VERSION = (0, 2, 0, "a", 1) # following PEP 386
DEV_N = 4


def get_version():
    version = "{0}.{1}".format(VERSION[0], VERSION[1])
    if VERSION[2]:
        version = "{0}.{1}".format(version, VERSION[2])
    if VERSION[3] != "f":
        version = "{0}{1}{2}".format(version, VERSION[3], VERSION[4])
        if DEV_N:
            version = "{0}.dev{1}".format(version, DEV_N)
    return version


__version__ = get_version()
