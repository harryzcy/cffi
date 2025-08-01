import pytest
from cffi import FFI, VerificationError, CDefError
from cffi.recompiler import make_py_source
from testing.udir import udir

pytestmark = [
    pytest.mark.thread_unsafe(reason="worker threads would share a compilation directory"),
]

def test_simple():
    ffi = FFI()
    ffi.cdef("int close(int); static const int BB = 42; extern int somevar;")
    target = udir.join('test_simple.py')
    make_py_source(ffi, 'test_simple', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI('test_simple',
    _version = 0x2601,
    _types = b'\x00\x00\x01\x0D\x00\x00\x07\x01\x00\x00\x00\x0F',
    _globals = (b'\xFF\xFF\xFF\x1FBB',42,b'\x00\x00\x00\x23close',0,b'\x00\x00\x01\x21somevar',0),
)
"""

def test_global_constant():
    ffi = FFI()
    ffi.cdef("static const long BB; static const float BF = 12;")
    target = udir.join('test_valid_global_constant.py')
    make_py_source(ffi, 'test_valid_global_constant', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI('test_valid_global_constant',
    _version = 0x2601,
    _types = b'\x00\x00\x0D\x01\x00\x00\x09\x01',
    _globals = (b'\x00\x00\x01\x25BB',0,b'\x00\x00\x00\x25BF',0),
)
"""

def test_invalid_global_constant_3():
    ffi = FFI()
    e = pytest.raises(CDefError, ffi.cdef, "#define BB 12.34")
    assert str(e.value).startswith(
        "only supports one of the following syntax:")

def test_invalid_dotdotdot_in_macro():
    ffi = FFI()
    ffi.cdef("#define FOO ...")
    target = udir.join('test_invalid_dotdotdot_in_macro.py')
    e = pytest.raises(VerificationError, make_py_source, ffi,
                       'test_invalid_dotdotdot_in_macro', str(target))
    assert str(e.value) == ("macro FOO: cannot use the syntax '...' in "
                            "'#define FOO ...' when using the ABI mode")

def test_typename():
    ffi = FFI()
    ffi.cdef("typedef int foobar_t;")
    target = udir.join('test_typename.py')
    make_py_source(ffi, 'test_typename', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI('test_typename',
    _version = 0x2601,
    _types = b'\x00\x00\x07\x01',
    _typenames = (b'\x00\x00\x00\x00foobar_t',),
)
"""

def test_enum():
    ffi = FFI()
    ffi.cdef("enum myenum_e { AA, BB, CC=-42 };")
    target = udir.join('test_enum.py')
    make_py_source(ffi, 'test_enum', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI('test_enum',
    _version = 0x2601,
    _types = b'\x00\x00\x00\x0B',
    _globals = (b'\xFF\xFF\xFF\x0BAA',0,b'\xFF\xFF\xFF\x0BBB',1,b'\xFF\xFF\xFF\x0BCC',-42),
    _enums = (b'\x00\x00\x00\x00\x00\x00\x00\x15myenum_e\x00AA,BB,CC',),
)
"""

def test_struct():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a; signed char b[]; }; struct bar_s;")
    target = udir.join('test_struct.py')
    make_py_source(ffi, 'test_struct', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI('test_struct',
    _version = 0x2601,
    _types = b'\x00\x00\x07\x01\x00\x00\x03\x01\x00\x00\x01\x07\x00\x00\x00\x09\x00\x00\x01\x09',
    _struct_unions = ((b'\x00\x00\x00\x03\x00\x00\x00\x10bar_s',),(b'\x00\x00\x00\x04\x00\x00\x00\x02foo_s',b'\x00\x00\x00\x11a',b'\x00\x00\x02\x11b')),
)
"""

def test_include():
    ffi = FFI()
    ffi.cdef("#define ABC 123")
    ffi.set_source('test_include', None)
    target = udir.join('test_include.py')
    make_py_source(ffi, 'test_include', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI('test_include',
    _version = 0x2601,
    _types = b'',
    _globals = (b'\xFF\xFF\xFF\x1FABC',123,),
)
"""
    #
    ffi2 = FFI()
    ffi2.include(ffi)
    target2 = udir.join('test2_include.py')
    make_py_source(ffi2, 'test2_include', str(target2))
    assert target2.read() == r"""# auto-generated file
import _cffi_backend
from test_include import ffi as _ffi0

ffi = _cffi_backend.FFI('test2_include',
    _version = 0x2601,
    _types = b'',
    _includes = (_ffi0,),
)
"""

def test_negative_constant():
    ffi = FFI()
    ffi.cdef("static const int BB = -42;")
    target = udir.join('test_negative_constant.py')
    make_py_source(ffi, 'test_negative_constant', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI('test_negative_constant',
    _version = 0x2601,
    _types = b'',
    _globals = (b'\xFF\xFF\xFF\x1FBB',-42,),
)
"""

def test_struct_included():
    baseffi = FFI()
    baseffi.cdef("struct foo_s { int x; };")
    baseffi.set_source('test_struct_included_base', None)
    #
    ffi = FFI()
    ffi.include(baseffi)
    target = udir.join('test_struct_included.py')
    make_py_source(ffi, 'test_struct_included', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend
from test_struct_included_base import ffi as _ffi0

ffi = _cffi_backend.FFI('test_struct_included',
    _version = 0x2601,
    _types = b'\x00\x00\x00\x09',
    _struct_unions = ((b'\x00\x00\x00\x00\x00\x00\x00\x08foo_s',),),
    _includes = (_ffi0,),
)
"""

def test_no_cross_include():
    baseffi = FFI()
    baseffi.set_source('test_no_cross_include_base', "..source..")
    #
    ffi = FFI()
    ffi.include(baseffi)
    target = udir.join('test_no_cross_include.py')
    pytest.raises(VerificationError, make_py_source,
                   ffi, 'test_no_cross_include', str(target))

def test_array():
    ffi = FFI()
    ffi.cdef("typedef int32_t my_array_t[42];")
    target = udir.join('test_array.py')
    make_py_source(ffi, 'test_array', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI('test_array',
    _version = 0x2601,
    _types = b'\x00\x00\x15\x01\x00\x00\x00\x05\x00\x00\x00\x2A',
    _typenames = (b'\x00\x00\x00\x01my_array_t',),
)
"""

def test_array_overflow():
    ffi = FFI()
    ffi.cdef("typedef int32_t my_array_t[3000000000];")
    target = udir.join('test_array_overflow.py')
    pytest.raises(OverflowError, make_py_source,
                   ffi, 'test_array_overflow', str(target))

def test_global_var():
    ffi = FFI()
    ffi.cdef("extern int myglob;")
    target = udir.join('test_global_var.py')
    make_py_source(ffi, 'test_global_var', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI('test_global_var',
    _version = 0x2601,
    _types = b'\x00\x00\x07\x01',
    _globals = (b'\x00\x00\x00\x21myglob',0,),
)
"""

def test_bitfield():
    ffi = FFI()
    ffi.cdef("struct foo_s { int y:10; short x:5; };")
    target = udir.join('test_bitfield.py')
    make_py_source(ffi, 'test_bitfield', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI('test_bitfield',
    _version = 0x2601,
    _types = b'\x00\x00\x07\x01\x00\x00\x05\x01\x00\x00\x00\x09',
    _struct_unions = ((b'\x00\x00\x00\x02\x00\x00\x00\x02foo_s',b'\x00\x00\x00\x13\x00\x00\x00\x0Ay',b'\x00\x00\x01\x13\x00\x00\x00\x05x'),),
)
"""
