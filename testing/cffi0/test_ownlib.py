import sys, os
import subprocess, weakref
import pytest
from cffi import FFI
from cffi.backend_ctypes import CTypesBackend
from testing.support import u, is_musl


SOURCE = """\
#include <errno.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

EXPORT int test_getting_errno(void) {
    errno = 123;
    return -1;
}

EXPORT int test_setting_errno(void) {
    return errno;
};

typedef struct {
    long x;
    long y;
} POINT;

typedef struct {
    long left;
    long top;
    long right;
    long bottom;
} RECT;

typedef struct {
    unsigned char a, b, c;
} THREEBYTES;


EXPORT int PointInRect(RECT *prc, POINT pt)
{
    if (pt.x < prc->left)
        return 0;
    if (pt.x > prc->right)
        return 0;
    if (pt.y < prc->top)
        return 0;
    if (pt.y > prc->bottom)
        return 0;
    return 1;
};

EXPORT long left = 10;
EXPORT long top = 20;
EXPORT long right = 30;
EXPORT long bottom = 40;

EXPORT RECT ReturnRect(int i, RECT ar, RECT* br, POINT cp, RECT dr,
                        RECT *er, POINT fp, RECT gr)
{
    /*Check input */
    if (ar.left + br->left + dr.left + er->left + gr.left != left * 5)
    {
        ar.left = 100;
        return ar;
    }
    if (ar.right + br->right + dr.right + er->right + gr.right != right * 5)
    {
        ar.right = 100;
        return ar;
    }
    if (cp.x != fp.x)
    {
        ar.left = -100;
    }
    if (cp.y != fp.y)
    {
        ar.left = -200;
    }
    switch(i)
    {
    case 0:
        return ar;
        break;
    case 1:
        return dr;
        break;
    case 2:
        return gr;
        break;

    }
    return ar;
}

EXPORT int my_array[7] = {0, 1, 2, 3, 4, 5, 6};

EXPORT unsigned short foo_2bytes(unsigned short a)
{
    return (unsigned short)(a + 42);
}
EXPORT unsigned int foo_4bytes(unsigned int a)
{
    return (unsigned int)(a + 42);
}

EXPORT void modify_struct_value(RECT r)
{
    r.left = r.right = r.top = r.bottom = 500;
}

EXPORT THREEBYTES return_three_bytes(void)
{
    THREEBYTES result;
    result.a = 12;
    result.b = 34;
    result.c = 56;
    return result;
}
"""

@pytest.mark.thread_unsafe(reason="Parallel tests would share a build directory")
class TestOwnLib(object):
    Backend = CTypesBackend

    def setup_class(cls):
        cls.module = None
        from testing.udir import udir
        udir.join('testownlib.c').write(SOURCE)
        if sys.platform == 'win32':
            # did we already build it?
            if cls.Backend is CTypesBackend:
                dll_path = str(udir) + '\\testownlib1.dll'   # only ascii for the ctypes backend
            else:
                dll_path = str(udir) + '\\' + (u+'testownlib\u03be.dll')   # non-ascii char
            if os.path.exists(dll_path):
                cls.module = dll_path
                return
            # try (not too hard) to find the version used to compile this python
            # no mingw
            from distutils.msvc9compiler import get_build_version
            version = get_build_version()
            toolskey = "VS%0.f0COMNTOOLS" % version
            toolsdir = os.environ.get(toolskey, None)
            if toolsdir is None:
                return
            productdir = os.path.join(toolsdir, os.pardir, os.pardir, "VC")
            productdir = os.path.abspath(productdir)
            vcvarsall = os.path.join(productdir, "vcvarsall.bat")
            # 64?
            arch = 'x86'
            if sys.maxsize > 2**32:
                arch = 'amd64'
            if os.path.isfile(vcvarsall):
                cmd = '"%s" %s' % (vcvarsall, arch) + ' & cl.exe testownlib.c ' \
                        ' /LD /Fetestownlib.dll'
                subprocess.check_call(cmd, cwd = str(udir), shell=True)
                os.rename(str(udir) + '\\testownlib.dll', dll_path)
                cls.module = dll_path
        else:
            encoded = None
            if cls.Backend is not CTypesBackend:
                try:
                    unicode_name = u+'testownlibcaf\xe9'
                    encoded = unicode_name.encode(sys.getfilesystemencoding())
                    if sys.version_info >= (3,):
                        encoded = str(unicode_name)
                except UnicodeEncodeError:
                    pass
            if encoded is None:
                unicode_name = u+'testownlib'
                encoded = str(unicode_name)
            subprocess.check_call(
                "cc testownlib.c -shared -fPIC -o '%s.so'" % (encoded,),
                cwd=str(udir), shell=True)
            cls.module = os.path.join(str(udir), unicode_name + (u+'.so'))
        print(repr(cls.module))

    def test_getting_errno(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        if sys.platform == 'win32':
            pytest.skip("fails, errno at multiple addresses")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int test_getting_errno(void);
        """)
        ownlib = ffi.dlopen(self.module)
        res = ownlib.test_getting_errno()
        assert res == -1
        assert ffi.errno == 123

    def test_setting_errno(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        if sys.platform == 'win32':
            pytest.skip("fails, errno at multiple addresses")
        if self.Backend is CTypesBackend and '__pypy__' in sys.modules:
            pytest.skip("XXX errno issue with ctypes on pypy?")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int test_setting_errno(void);
        """)
        ownlib = ffi.dlopen(self.module)
        ffi.errno = 42
        res = ownlib.test_setting_errno()
        assert res == 42
        assert ffi.errno == 42

    def test_my_array_7(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            extern int my_array[7];
        """)
        ownlib = ffi.dlopen(self.module)
        for i in range(7):
            assert ownlib.my_array[i] == i
        assert len(ownlib.my_array) == 7
        if self.Backend is CTypesBackend:
            pytest.skip("not supported by the ctypes backend")
        ownlib.my_array = list(range(10, 17))
        for i in range(7):
            assert ownlib.my_array[i] == 10 + i
        ownlib.my_array = list(range(7))
        for i in range(7):
            assert ownlib.my_array[i] == i

    def test_my_array_no_length(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        if self.Backend is CTypesBackend:
            pytest.skip("not supported by the ctypes backend")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            extern int my_array[];
        """)
        ownlib = ffi.dlopen(self.module)
        for i in range(7):
            assert ownlib.my_array[i] == i
        pytest.raises(TypeError, len, ownlib.my_array)
        ownlib.my_array = list(range(10, 17))
        for i in range(7):
            assert ownlib.my_array[i] == 10 + i
        ownlib.my_array = list(range(7))
        for i in range(7):
            assert ownlib.my_array[i] == i

    def test_keepalive_lib(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int test_getting_errno(void);
        """)
        ownlib = ffi.dlopen(self.module)
        ffi_r = weakref.ref(ffi)
        ownlib_r = weakref.ref(ownlib)
        func = ownlib.test_getting_errno
        del ffi
        import gc; gc.collect()       # ownlib stays alive
        assert ownlib_r() is not None
        assert ffi_r() is not None    # kept alive by ownlib
        res = func()
        assert res == -1

    def test_keepalive_ffi(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int test_getting_errno(void);
        """)
        ownlib = ffi.dlopen(self.module)
        ffi_r = weakref.ref(ffi)
        ownlib_r = weakref.ref(ownlib)
        func = ownlib.test_getting_errno
        del ownlib
        import gc; gc.collect()       # ffi stays alive
        assert ffi_r() is not None
        assert ownlib_r() is not None # kept alive by ffi
        res = func()
        assert res == -1
        if sys.platform != 'win32':  # else, errno at multiple addresses
            assert ffi.errno == 123

    def test_struct_by_value(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            typedef struct {
                long x;
                long y;
            } POINT;

            typedef struct {
                long left;
                long top;
                long right;
                long bottom;
            } RECT;
            
            extern long left, top, right, bottom;

            RECT ReturnRect(int i, RECT ar, RECT* br, POINT cp, RECT dr,
                        RECT *er, POINT fp, RECT gr);
        """)
        ownlib = ffi.dlopen(self.module)

        rect = ffi.new('RECT[1]')
        pt = ffi.new('POINT[1]')
        pt[0].x = 15
        pt[0].y = 25
        rect[0].left = ownlib.left
        rect[0].right = ownlib.right
        rect[0].top = ownlib.top
        rect[0].bottom = ownlib.bottom
        
        for i in range(4):
            ret = ownlib.ReturnRect(i, rect[0], rect, pt[0], rect[0],
                                    rect, pt[0], rect[0])
            assert ret.left == ownlib.left
            assert ret.right == ownlib.right
            assert ret.top == ownlib.top
            assert ret.bottom == ownlib.bottom

    def test_addressof_lib(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        if self.Backend is CTypesBackend:
            pytest.skip("not implemented with the ctypes backend")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("extern long left; int test_getting_errno(void);")
        lib = ffi.dlopen(self.module)
        lib.left = 123456
        p = ffi.addressof(lib, "left")
        assert ffi.typeof(p) == ffi.typeof("long *")
        assert p[0] == 123456
        p[0] += 1
        assert lib.left == 123457
        pfn = ffi.addressof(lib, "test_getting_errno")
        assert ffi.typeof(pfn) == ffi.typeof("int(*)(void)")
        assert pfn == lib.test_getting_errno

    def test_char16_char32_t(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        if self.Backend is CTypesBackend:
            pytest.skip("not implemented with the ctypes backend")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            char16_t foo_2bytes(char16_t);
            char32_t foo_4bytes(char32_t);
        """)
        lib = ffi.dlopen(self.module)
        assert lib.foo_2bytes(u+'\u1234') == u+'\u125e'
        assert lib.foo_4bytes(u+'\u1234') == u+'\u125e'
        assert lib.foo_4bytes(u+'\U00012345') == u+'\U0001236f'

    def test_modify_struct_value(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        if self.Backend is CTypesBackend:
            pytest.skip("fails with the ctypes backend on some architectures")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            typedef struct {
                long left;
                long top;
                long right;
                long bottom;
            } RECT;

            void modify_struct_value(RECT r);
        """)
        lib = ffi.dlopen(self.module)
        s = ffi.new("RECT *", [11, 22, 33, 44])
        lib.modify_struct_value(s[0])
        assert s.left == 11
        assert s.top == 22
        assert s.right == 33
        assert s.bottom == 44

    def test_dlopen_handle(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        if sys.platform == 'win32' or is_musl or sys.platform.startswith('freebsd'):
            pytest.skip("uses 'dl' explicitly")
        if self.__class__.Backend is CTypesBackend:
            pytest.skip("not for the ctypes backend")
        backend = self.Backend()
        ffi1 = FFI(backend=backend)
        ffi1.cdef("""void *dlopen(const char *filename, int flags);
                     int dlclose(void *handle);""")
        lib1 = ffi1.dlopen('dl')
        handle = lib1.dlopen(self.module.encode(sys.getfilesystemencoding()),
                             backend.RTLD_LAZY)
        assert ffi1.typeof(handle) == ffi1.typeof("void *")
        assert handle

        ffi = FFI(backend=backend)
        ffi.cdef("""unsigned short foo_2bytes(unsigned short a);""")
        lib = ffi.dlopen(handle)
        x = lib.foo_2bytes(1000)
        assert x == 1042

        err = lib1.dlclose(handle)
        assert err == 0

    def test_return_three_bytes(self):
        if self.module is None:
            pytest.skip("fix the auto-generation of the tiny test lib")
        if self.__class__.Backend is CTypesBackend:
            pytest.skip("not working on win32 on the ctypes backend")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            typedef struct {
                unsigned char a, b, c;
            } THREEBYTES;

            THREEBYTES return_three_bytes(void);
        """)
        lib = ffi.dlopen(self.module)
        tb = lib.return_three_bytes()
        assert tb.a == 12
        assert tb.b == 34
        assert tb.c == 56
