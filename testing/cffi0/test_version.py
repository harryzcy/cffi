import os, sys
import pytest
import cffi, _cffi_backend
from pathlib import Path

def setup_module(mod):
    if '_cffi_backend' in sys.builtin_module_names:
        pytest.skip("this is embedded version")

#BACKEND_VERSIONS = {
#    '0.4.2': '0.4',     # did not change
#    '0.7.1': '0.7',     # did not change
#    '0.7.2': '0.7',     # did not change
#    '0.8.1': '0.8',     # did not change (essentially)
#    '0.8.4': '0.8.3',   # did not change
#    }

def _read(p):
    with open(p) as f:
        return f.read()

def test_version():
    v = cffi.__version__
    version_info = '.'.join(str(i) for i in cffi.__version_info__)
    version_info = version_info.replace('.b', 'b')
    version_info = version_info.replace('.plus', '+')
    version_info = version_info.replace('.rc', 'rc')
    assert v == version_info
    #v = BACKEND_VERSIONS.get(v, v)
    assert v == _cffi_backend.__version__

def test_doc_version():
    cffi_root = Path(os.path.dirname(__file__)).parent.parent
    p = cffi_root / 'doc/source/conf.py'
    content = _read(p)
    #
    v = cffi.__version__
    assert ("version = '%s'\n" % ".".join(v.split('.')[:2])) in content
    assert ("release = '%s'\n" % v) in content

def test_pyproject_version():
    cffi_root = Path(os.path.dirname(__file__)).parent.parent
    p = cffi_root / 'pyproject.toml'
    content = _read(p)
    #
    v = cffi.__version__.replace('+', '')
    assert f'version = "{v}"' in content

def test_c_version():
    cffi_root = Path(os.path.dirname(__file__)).parent.parent
    v = cffi.__version__
    p = cffi_root / 'src/c/test_c.py'
    content = _read(p)
    #v = BACKEND_VERSIONS.get(v, v)
    assert (('assert __version__ == "%s"' % v) in content)

def test_embedding_h():
    cffi_root = Path(os.path.dirname(__file__)).parent.parent
    v = cffi.__version__
    p = cffi_root / 'src/cffi/_embedding.h'
    content = _read(p)
    assert ('cffi version: %s"' % (v,)) in content
