import pytest
from cffi import FFI, CDefError
import math, os, sys
import ctypes.util
from cffi.backend_ctypes import CTypesBackend
from testing.udir import udir
from testing.support import FdWriteCapture, StdErrCapture, is_musl
from .backend_tests import needs_dlopen_none

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

try:
    from packaging.tags import platform_tags
    _platform_tags_cached = set(platform_tags())
    _is_musl = any(t.startswith('musllinux') for t in _platform_tags_cached)
except ImportError:
    _is_musl = False

lib_m = 'm'
if sys.platform == 'win32':
    #there is a small chance this fails on Mingw via environ $CC
    import distutils.ccompiler
    if distutils.ccompiler.get_default_compiler() == 'msvc':
        lib_m = 'msvcrt'
elif is_musl:
    lib_m = 'c'

class TestFunction(object):
    Backend = CTypesBackend

    def test_sin(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            double sin(double x);
        """)
        m = ffi.dlopen(lib_m)
        x = m.sin(1.23)
        assert x == math.sin(1.23)

    def test_sinf(self):
        if sys.platform == 'win32':
            pytest.skip("no sinf found in the Windows stdlib")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            float sinf(float x);
        """)
        m = ffi.dlopen(lib_m)
        x = m.sinf(1.23)
        assert type(x) is float
        assert x != math.sin(1.23)    # rounding effects
        assert abs(x - math.sin(1.23)) < 1E-6

    def test_getenv_no_return_value(self):
        # check that 'void'-returning functions work too
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            void getenv(char *);
        """)
        needs_dlopen_none()
        m = ffi.dlopen(None)
        x = m.getenv(b"FOO")
        assert x is None

    def test_dlopen_filename(self):
        path = ctypes.util.find_library(lib_m)
        if not path:
            pytest.skip("%s not found" % lib_m)
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            double cos(double x);
        """)
        m = ffi.dlopen(path)
        x = m.cos(1.23)
        assert x == math.cos(1.23)

        m = ffi.dlopen(os.path.basename(path))
        x = m.cos(1.23)
        assert x == math.cos(1.23)

    def test_dlopen_flags(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            double cos(double x);
        """)
        m = ffi.dlopen(lib_m, ffi.RTLD_LAZY | ffi.RTLD_LOCAL)
        x = m.cos(1.23)
        assert x == math.cos(1.23)

    def test_dlopen_constant(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            #define FOOBAR 42
            static const float baz = 42.5;   /* not visible */
            double sin(double x);
        """)
        m = ffi.dlopen(lib_m)
        assert m.FOOBAR == 42
        with pytest.raises(NotImplementedError):
            m.baz

    def test_tlsalloc(self):
        if sys.platform != 'win32':
            pytest.skip("win32 only")
        if self.Backend is CTypesBackend:
            pytest.skip("ctypes complains on wrong calling conv")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("long TlsAlloc(void); int TlsFree(long);")
        lib = ffi.dlopen('KERNEL32.DLL')
        x = lib.TlsAlloc()
        assert x != 0
        y = lib.TlsFree(x)
        assert y != 0

    @pytest.mark.thread_unsafe(reason="manipulates stderr")
    def test_fputs(self):
        if not sys.platform.startswith('linux'):
            pytest.skip("probably no symbol 'stderr' in the lib")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int fputs(const char *, void *);
            extern void *stderr;
        """)
        needs_dlopen_none()
        ffi.C = ffi.dlopen(None)
        ffi.C.fputs   # fetch before capturing, for easier debugging
        with FdWriteCapture() as fd:
            ffi.C.fputs(b"hello\n", ffi.C.stderr)
            ffi.C.fputs(b"  world\n", ffi.C.stderr)
        res = fd.getvalue()
        assert res == b'hello\n  world\n'

    @pytest.mark.thread_unsafe(reason="manipulates stderr")
    def test_fputs_without_const(self):
        if not sys.platform.startswith('linux'):
            pytest.skip("probably no symbol 'stderr' in the lib")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int fputs(char *, void *);
            extern void *stderr;
        """)
        needs_dlopen_none()
        ffi.C = ffi.dlopen(None)
        ffi.C.fputs   # fetch before capturing, for easier debugging
        with FdWriteCapture() as fd:
            ffi.C.fputs(b"hello\n", ffi.C.stderr)
            ffi.C.fputs(b"  world\n", ffi.C.stderr)
        res = fd.getvalue()
        assert res == b'hello\n  world\n'

    @pytest.mark.thread_unsafe(reason="manipulates stderr")
    def test_vararg(self):
        if not sys.platform.startswith('linux'):
            pytest.skip("probably no symbol 'stderr' in the lib")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
           int fprintf(void *, const char *format, ...);
           extern void *stderr;
        """)
        needs_dlopen_none()
        ffi.C = ffi.dlopen(None)
        with FdWriteCapture() as fd:
            ffi.C.fprintf(ffi.C.stderr, b"hello with no arguments\n")
            ffi.C.fprintf(ffi.C.stderr,
                          b"hello, %s!\n", ffi.new("char[]", b"world"))
            ffi.C.fprintf(ffi.C.stderr,
                          ffi.new("char[]", b"hello, %s!\n"),
                          ffi.new("char[]", b"world2"))
            ffi.C.fprintf(ffi.C.stderr,
                          b"hello int %d long %ld long long %lld\n",
                          ffi.cast("int", 42),
                          ffi.cast("long", 84),
                          ffi.cast("long long", 168))
            ffi.C.fprintf(ffi.C.stderr, b"hello %p\n", ffi.NULL)
        res = fd.getvalue()
        if is_musl:
            nil_repr = b'0'
        else:
            nil_repr = b'(nil)'
        assert res == (b"hello with no arguments\n"
                       b"hello, world!\n"
                       b"hello, world2!\n"
                       b"hello int 42 long 84 long long 168\n"
                       b"hello " + nil_repr + b"\n")

    def test_must_specify_type_of_vararg(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
           int printf(const char *format, ...);
        """)
        needs_dlopen_none()
        ffi.C = ffi.dlopen(None)
        e = pytest.raises(TypeError, ffi.C.printf, b"hello %d\n", 42)
        assert str(e.value) == ("argument 2 passed in the variadic part "
                                "needs to be a cdata object (got int)")

    def test_function_has_a_c_type(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int puts(const char *);
        """)
        needs_dlopen_none()
        ffi.C = ffi.dlopen(None)
        fptr = ffi.C.puts
        assert ffi.typeof(fptr) == ffi.typeof("int(*)(const char*)")
        if self.Backend is CTypesBackend:
            assert repr(fptr).startswith("<cdata 'int puts(char *)' 0x")

    @pytest.mark.thread_unsafe(reason="manipulates stderr")
    def test_function_pointer(self):
        ffi = FFI(backend=self.Backend())
        def cb(charp):
            assert repr(charp).startswith("<cdata 'char *' 0x")
            return 42
        fptr = ffi.callback("int(*)(const char *txt)", cb)
        assert fptr != ffi.callback("int(*)(const char *)", cb)
        assert repr(fptr) == "<cdata 'int(*)(char *)' calling %r>" % (cb,)
        res = fptr(b"Hello")
        assert res == 42
        #
        if not sys.platform.startswith('linux'):
            pytest.skip("probably no symbol 'stderr' in the lib")
        ffi.cdef("""
            int fputs(const char *, void *);
            extern void *stderr;
        """)
        needs_dlopen_none()
        ffi.C = ffi.dlopen(None)
        fptr = ffi.cast("int(*)(const char *txt, void *)", ffi.C.fputs)
        assert fptr == ffi.C.fputs
        assert repr(fptr).startswith("<cdata 'int(*)(char *, void *)' 0x")
        with FdWriteCapture() as fd:
            fptr(b"world\n", ffi.C.stderr)
        res = fd.getvalue()
        assert res == b'world\n'

    @pytest.mark.thread_unsafe(reason="manipulates stderr")
    def test_callback_returning_void(self):
        ffi = FFI(backend=self.Backend())
        for returnvalue in [None, 42]:
            def cb():
                return returnvalue
            fptr = ffi.callback("void(*)(void)", cb)
            with StdErrCapture() as f:
                returned = fptr()
            printed = f.getvalue()
            assert returned is None
            if returnvalue is None:
                assert printed == ''
            else:
                assert "None" in printed

    def test_callback_returning_struct_three_bytes(self):
        if self.Backend is CTypesBackend:
            pytest.skip("not supported with the ctypes backend")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            typedef struct {
                unsigned char a, b, c;
            } THREEBYTES;
        """)
        def cb():
            return (12, 34, 56)
        fptr = ffi.callback("THREEBYTES(*)(void)", cb)
        tb = fptr()
        assert tb.a == 12
        assert tb.b == 34
        assert tb.c == 56

    def test_passing_array(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int strlen(char[]);
        """)
        needs_dlopen_none()
        ffi.C = ffi.dlopen(None)
        p = ffi.new("char[]", b"hello")
        res = ffi.C.strlen(p)
        assert res == 5

    def test_write_variable(self):
        if not sys.platform.startswith('linux') or _is_musl:
            pytest.skip("probably no symbol 'stdout' in the lib")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            extern void *stdout;
        """)
        needs_dlopen_none()
        C = ffi.dlopen(None)
        pout = C.stdout
        C.stdout = ffi.NULL
        assert C.stdout == ffi.NULL
        C.stdout = pout
        assert C.stdout == pout

    def test_strchr(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            char *strchr(const char *s, int c);
        """)
        needs_dlopen_none()
        ffi.C = ffi.dlopen(None)
        p = ffi.new("char[]", b"hello world!")
        q = ffi.C.strchr(p, ord('w'))
        assert ffi.string(q) == b"world!"

    def test_function_with_struct_argument(self):
        if sys.platform == 'win32':
            pytest.skip("no 'inet_ntoa'")
        if (self.Backend is CTypesBackend and
            '__pypy__' in sys.builtin_module_names):
            pytest.skip("ctypes limitation on pypy")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            struct in_addr { unsigned int s_addr; };
            char *inet_ntoa(struct in_addr in);
        """)
        needs_dlopen_none()
        ffi.C = ffi.dlopen(None)
        ina = ffi.new("struct in_addr *", [0x04040404])
        a = ffi.C.inet_ntoa(ina[0])
        assert ffi.string(a) == b'4.4.4.4'

    def test_function_typedef(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            typedef double func_t(double);
            func_t sin;
        """)
        m = ffi.dlopen(lib_m)
        x = m.sin(1.23)
        assert x == math.sin(1.23)

    @pytest.mark.thread_unsafe(reason="workers would share a file descriptor")
    def test_fputs_custom_FILE(self):
        if self.Backend is CTypesBackend:
            pytest.skip("FILE not supported with the ctypes backend")
        filename = str(udir.join('fputs_custom_FILE'))
        ffi = FFI(backend=self.Backend())
        ffi.cdef("int fputs(const char *, FILE *);")
        needs_dlopen_none()
        C = ffi.dlopen(None)
        with open(filename, 'wb') as f:
            f.write(b'[')
            C.fputs(b"hello from custom file", f)
            f.write(b'][')
            C.fputs(b"some more output", f)
            f.write(b']')
        with open(filename, 'rb') as f:
            res = f.read()
        assert res == b'[hello from custom file][some more output]'

    def test_constants_on_lib(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""enum foo_e { AA, BB, CC=5, DD };
                    typedef enum { EE=-5, FF } some_enum_t;""")
        needs_dlopen_none()
        lib = ffi.dlopen(None)
        assert lib.AA == 0
        assert lib.BB == 1
        assert lib.CC == 5
        assert lib.DD == 6
        assert lib.EE == -5
        assert lib.FF == -4

    def test_void_star_accepts_string(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""int strlen(const void *);""")
        needs_dlopen_none()
        lib = ffi.dlopen(None)
        res = lib.strlen(b"hello")
        assert res == 5

    def test_signed_char_star_accepts_string(self):
        if self.Backend is CTypesBackend:
            pytest.skip("not supported by the ctypes backend")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""int strlen(signed char *);""")
        needs_dlopen_none()
        lib = ffi.dlopen(None)
        res = lib.strlen(b"hello")
        assert res == 5

    def test_unsigned_char_star_accepts_string(self):
        if self.Backend is CTypesBackend:
            pytest.skip("not supported by the ctypes backend")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""int strlen(unsigned char *);""")
        needs_dlopen_none()
        lib = ffi.dlopen(None)
        res = lib.strlen(b"hello")
        assert res == 5

    def test_missing_function(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int nonexistent();
        """)
        m = ffi.dlopen(lib_m)
        assert not hasattr(m, 'nonexistent')

    def test_wraps_from_stdlib(self):
        import functools
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            double sin(double x);
        """)
        def my_decorator(f):
            @functools.wraps(f)
            def wrapper(*args):
                return f(*args) + 100
            return wrapper
        m = ffi.dlopen(lib_m)
        sin100 = my_decorator(m.sin)
        x = sin100(1.23)
        assert x == math.sin(1.23) + 100

    @pytest.mark.thread_unsafe(
        reason="may fail if other threads trigger garbage collection")
    def test_free_callback_cycle(self):
        if self.Backend is CTypesBackend:
            pytest.skip("seems to fail with the ctypes backend on windows")
        import weakref
        def make_callback(data):
            container = [data]
            callback = ffi.callback('int()', lambda: len(container))
            container.append(callback)
            # Ref cycle: callback -> lambda (closure) -> container -> callback
            return callback

        class Data(object):
            pass
        ffi = FFI(backend=self.Backend())
        data = Data()
        callback = make_callback(data)
        wr = weakref.ref(data)
        del callback, data
        for i in range(3):
            if wr() is not None:
                import gc; gc.collect()
        assert wr() is None    # 'data' does not leak

    def test_windows_stdcall(self):
        if sys.platform != 'win32':
            pytest.skip("Windows-only test")
        if self.Backend is CTypesBackend:
            pytest.skip("not with the ctypes backend")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            BOOL QueryPerformanceFrequency(LONGLONG *lpFrequency);
        """)
        m = ffi.dlopen("Kernel32.dll")
        p_freq = ffi.new("LONGLONG *")
        res = m.QueryPerformanceFrequency(p_freq)
        assert res != 0
        assert p_freq[0] != 0

    def test_explicit_cdecl_stdcall(self):
        if sys.platform != 'win32':
            pytest.skip("Windows-only test")
        if self.Backend is CTypesBackend:
            pytest.skip("not with the ctypes backend")
        win64 = (sys.maxsize > 2**32)
        #
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            BOOL QueryPerformanceFrequency(LONGLONG *lpFrequency);
        """)
        m = ffi.dlopen("Kernel32.dll")
        tp = ffi.typeof(m.QueryPerformanceFrequency)
        assert str(tp) == "<ctype 'int(*)(long long *)'>"
        #
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            BOOL __cdecl QueryPerformanceFrequency(LONGLONG *lpFrequency);
        """)
        m = ffi.dlopen("Kernel32.dll")
        tpc = ffi.typeof(m.QueryPerformanceFrequency)
        assert tpc is tp
        #
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            BOOL WINAPI QueryPerformanceFrequency(LONGLONG *lpFrequency);
        """)
        m = ffi.dlopen("Kernel32.dll")
        tps = ffi.typeof(m.QueryPerformanceFrequency)
        if win64:
            assert tps is tpc
        else:
            assert tps is not tpc
            assert str(tps) == "<ctype 'int(__stdcall *)(long long *)'>"
        #
        ffi = FFI(backend=self.Backend())
        ffi.cdef("typedef int (__cdecl *fnc_t)(int);")
        ffi.cdef("typedef int (__stdcall *fns_t)(int);")
        tpc = ffi.typeof("fnc_t")
        tps = ffi.typeof("fns_t")
        assert str(tpc) == "<ctype 'int(*)(int)'>"
        if win64:
            assert tps is tpc
        else:
            assert str(tps) == "<ctype 'int(__stdcall *)(int)'>"
        #
        fnc = ffi.cast("fnc_t", 0)
        fns = ffi.cast("fns_t", 0)
        ffi.new("fnc_t[]", [fnc])
        if not win64:
            pytest.raises(TypeError, ffi.new, "fnc_t[]", [fns])
            pytest.raises(TypeError, ffi.new, "fns_t[]", [fnc])
        ffi.new("fns_t[]", [fns])

    def test_stdcall_only_on_windows(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("double __stdcall sin(double x);")     # stdcall ignored
        m = ffi.dlopen(lib_m)
        if (sys.platform == 'win32' and sys.maxsize < 2**32 and
                self.Backend is not CTypesBackend):
            assert "double(__stdcall *)(double)" in str(ffi.typeof(m.sin))
        else:
            assert "double(*)(double)" in str(ffi.typeof(m.sin))
        x = m.sin(1.23)
        assert x == math.sin(1.23)

    def test_dir_on_dlopen_lib(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            typedef enum { MYE1, MYE2 } myenum_t;
            double myfunc(double);
            extern double myvar;
            const double myconst;
            #define MYFOO 42
        """)
        m = ffi.dlopen(lib_m)
        assert dir(m) == ['MYE1', 'MYE2', 'MYFOO', 'myconst', 'myfunc', 'myvar']

    @pytest.mark.thread_unsafe(
        reason="Worker threads might call dlclose simultaneously")
    def test_dlclose(self):
        if self.Backend is CTypesBackend:
            pytest.skip("not with the ctypes backend")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("int foobar(void); extern int foobaz;")
        lib = ffi.dlopen(lib_m)
        ffi.dlclose(lib)
        e = pytest.raises(ValueError, getattr, lib, 'foobar')
        assert str(e.value).startswith("library '")
        assert str(e.value).endswith("' has already been closed")
        e = pytest.raises(ValueError, getattr, lib, 'foobaz')
        assert str(e.value).startswith("library '")
        assert str(e.value).endswith("' has already been closed")
        e = pytest.raises(ValueError, setattr, lib, 'foobaz', 42)
        assert str(e.value).startswith("library '")
        assert str(e.value).endswith("' has already been closed")
        ffi.dlclose(lib)    # does not raise

    def test_passing_large_list(self):
        if self.Backend is CTypesBackend:
            pytest.skip("the ctypes backend doesn't support this")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            void getenv(char *);
        """)
        needs_dlopen_none()
        m = ffi.dlopen(None)
        arg = [b"F", b"O", b"O"] + [b"\x00"] * 20000000
        x = m.getenv(arg)
        assert x is None
