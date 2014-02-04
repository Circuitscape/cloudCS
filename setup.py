try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

from cloud_cs import __version__, __author__, __email__

setup(
    name = 'cloudCS',
    version = __version__,
    author = __author__,
    author_email = __email__,
    packages = ['cloud_cs'],
    scripts = ['bin/cswebgui.py'],
    url = 'http://www.circuitscape.org/',
    license = 'LICENSE.txt',
    description = 'cloudCS allows multiple users to use Circuitscape on a cloud hosted infrastructure. It provides a browser based interface for Circuitscape, both on the desktop (standalone mode) and the cloud (multiuser mode).',
    long_description = open('README.txt').read(),
    install_requires=[
        'circuitscape >= 3.8.0',
        'tornado >= 3.1.1',
        'google-api-python-client',
        'sockjs-tornado'
    ],
)
