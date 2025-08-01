
import sys, os
import pytest
from cffi import FFI, VerificationError, FFIError, CDefError
from cffi import recompiler
from testing.udir import udir
from testing.support import u, long
from testing.support import FdWriteCapture, StdErrCapture, _verify

pytestmark = [
    pytest.mark.thread_unsafe(reason="worker threads would share a compilation directory"),
]

try:
    import importlib
except ImportError:
    importlib = None


def check_type_table(input, expected_output, included=None):
    ffi = FFI()
    if included:
        ffi1 = FFI()
        ffi1.cdef(included)
        ffi.include(ffi1)
    ffi.cdef(input)
    recomp = recompiler.Recompiler(ffi, 'testmod')
    recomp.collect_type_table()
    assert ''.join(map(str, recomp.cffi_types)) == expected_output

def verify(ffi, module_name, source, *args, **kwds):
    no_cpp = kwds.pop('no_cpp', False)
    ignore_warnings = kwds.pop('ignore_warnings', False)
    kwds.setdefault('undef_macros', ['NDEBUG'])
    module_name = '_CFFI_' + module_name
    ffi.set_source(module_name, source)
    if not os.environ.get('NO_CPP') and not no_cpp:   # test the .cpp mode too
        kwds.setdefault('source_extension', '.cpp')
        source = 'extern "C" {\n%s\n}' % (source,)
    elif sys.platform != 'win32' and not ignore_warnings:
        # add '-Werror' to the existing 'extra_compile_args' flags
        from testing.support import extra_compile_args
        kwds['extra_compile_args'] = (kwds.get('extra_compile_args', []) +
                                      extra_compile_args)
    if sys.platform == 'darwin':
        kwds['extra_link_args'] = (kwds.get('extra_link_args', []) +
                                     ['-stdlib=libc++'])
    return _verify(ffi, module_name, source, *args, **kwds)

def test_set_source_no_slashes():
    ffi = FFI()
    pytest.raises(ValueError, ffi.set_source, "abc/def", None)
    pytest.raises(ValueError, ffi.set_source, "abc/def", "C code")


def test_type_table_func():
    check_type_table("double sin(double);",
                     "(FUNCTION 1)(PRIMITIVE 14)(FUNCTION_END 0)")
    check_type_table("float sin(double);",
                     "(FUNCTION 3)(PRIMITIVE 14)(FUNCTION_END 0)(PRIMITIVE 13)")
    check_type_table("float sin(void);",
                     "(FUNCTION 2)(FUNCTION_END 0)(PRIMITIVE 13)")
    check_type_table("double sin(float); double cos(float);",
                     "(FUNCTION 3)(PRIMITIVE 13)(FUNCTION_END 0)(PRIMITIVE 14)")
    check_type_table("double sin(float); double cos(double);",
                     "(FUNCTION 1)(PRIMITIVE 14)(FUNCTION_END 0)"   # cos
                     "(FUNCTION 1)(PRIMITIVE 13)(FUNCTION_END 0)")  # sin
    check_type_table("float sin(double); float cos(float);",
                     "(FUNCTION 4)(PRIMITIVE 14)(FUNCTION_END 0)"   # sin
                     "(FUNCTION 4)(PRIMITIVE 13)(FUNCTION_END 0)")  # cos

def test_type_table_use_noop_for_repeated_args():
    check_type_table("double sin(double *, double *);",
                     "(FUNCTION 4)(POINTER 4)(NOOP 1)(FUNCTION_END 0)"
                     "(PRIMITIVE 14)")
    check_type_table("double sin(double *, double *, double);",
                     "(FUNCTION 3)(POINTER 3)(NOOP 1)(PRIMITIVE 14)"
                     "(FUNCTION_END 0)")

def test_type_table_dont_use_noop_for_primitives():
    check_type_table("double sin(double, double);",
                     "(FUNCTION 1)(PRIMITIVE 14)(PRIMITIVE 14)(FUNCTION_END 0)")

def test_type_table_funcptr_as_argument():
    check_type_table("int sin(double(float));",
                     "(FUNCTION 6)(PRIMITIVE 13)(FUNCTION_END 0)"
                     "(FUNCTION 7)(POINTER 0)(FUNCTION_END 0)"
                     "(PRIMITIVE 14)(PRIMITIVE 7)")

def test_type_table_variadic_function():
    check_type_table("int sin(int, ...);",
                     "(FUNCTION 1)(PRIMITIVE 7)(FUNCTION_END 1)(POINTER 0)")

def test_type_table_array():
    check_type_table("extern int a[100];",
                     "(PRIMITIVE 7)(ARRAY 0)(None 100)")

def test_type_table_typedef():
    check_type_table("typedef int foo_t;",
                     "(PRIMITIVE 7)")

def test_type_table_prebuilt_type():
    check_type_table("int32_t f(void);",
                     "(FUNCTION 2)(FUNCTION_END 0)(PRIMITIVE 21)")

def test_type_table_struct_opaque():
    check_type_table("struct foo_s;",
                     "(STRUCT_UNION 0)")

def test_type_table_struct():
    check_type_table("struct foo_s { int a; long b; };",
                     "(PRIMITIVE 7)(PRIMITIVE 9)(STRUCT_UNION 0)")

def test_type_table_union():
    check_type_table("union foo_u { int a; long b; };",
                     "(PRIMITIVE 7)(PRIMITIVE 9)(STRUCT_UNION 0)")

def test_type_table_struct_used():
    check_type_table("struct foo_s { int a; long b; }; int f(struct foo_s*);",
                     "(FUNCTION 3)(POINTER 5)(FUNCTION_END 0)"
                     "(PRIMITIVE 7)(PRIMITIVE 9)"
                     "(STRUCT_UNION 0)")

def test_type_table_anonymous_struct_with_typedef():
    check_type_table("typedef struct { int a; long b; } foo_t;",
                     "(STRUCT_UNION 0)(PRIMITIVE 7)(PRIMITIVE 9)")

def test_type_table_enum():
    check_type_table("enum foo_e { AA, BB, ... };",
                     "(ENUM 0)")

def test_type_table_include_1():
    check_type_table("foo_t sin(foo_t);",
                     "(FUNCTION 1)(PRIMITIVE 14)(FUNCTION_END 0)",
                     included="typedef double foo_t;")

def test_type_table_include_2():
    check_type_table("struct foo_s *sin(struct foo_s *);",
                     "(FUNCTION 1)(POINTER 3)(FUNCTION_END 0)(STRUCT_UNION 0)",
                     included="struct foo_s { int x, y; };")


def test_math_sin():
    import math
    ffi = FFI()
    ffi.cdef("float sin(double); double cos(double);")
    lib = verify(ffi, 'test_math_sin', '#include <math.h>',
                 ignore_warnings=True)
    assert lib.cos(1.43) == math.cos(1.43)

def test_repr_lib():
    ffi = FFI()
    lib = verify(ffi, 'test_repr_lib', '')
    assert repr(lib) == "<Lib object for '_CFFI_test_repr_lib'>"

def test_funcarg_ptr():
    ffi = FFI()
    ffi.cdef("int foo(int *);")
    lib = verify(ffi, 'test_funcarg_ptr', 'int foo(int *p) { return *p; }')
    assert lib.foo([-12345]) == -12345

def test_funcres_ptr():
    ffi = FFI()
    ffi.cdef("int *foo(void);")
    lib = verify(ffi, 'test_funcres_ptr',
                 'int *foo(void) { static int x=-12345; return &x; }')
    assert lib.foo()[0] == -12345

def test_global_var_array():
    ffi = FFI()
    ffi.cdef("extern int a[100];")
    lib = verify(ffi, 'test_global_var_array', 'int a[100] = { 9999 };')
    lib.a[42] = 123456
    assert lib.a[42] == 123456
    assert lib.a[0] == 9999

def test_verify_typedef():
    ffi = FFI()
    ffi.cdef("typedef int **foo_t;")
    lib = verify(ffi, 'test_verify_typedef', 'typedef int **foo_t;')
    assert ffi.sizeof("foo_t") == ffi.sizeof("void *")

def test_verify_typedef_dotdotdot():
    ffi = FFI()
    ffi.cdef("typedef ... foo_t;")
    verify(ffi, 'test_verify_typedef_dotdotdot', 'typedef int **foo_t;')

def test_verify_typedef_star_dotdotdot():
    ffi = FFI()
    ffi.cdef("typedef ... *foo_t;")
    verify(ffi, 'test_verify_typedef_star_dotdotdot', 'typedef int **foo_t;')

def test_global_var_int():
    ffi = FFI()
    ffi.cdef("extern int a, b, c;")
    lib = verify(ffi, 'test_global_var_int', 'int a = 999, b, c;')
    assert lib.a == 999
    lib.a -= 1001
    assert lib.a == -2
    lib.a = -2147483648
    assert lib.a == -2147483648
    with pytest.raises(OverflowError):
        lib.a = 2147483648
    with pytest.raises(OverflowError):
        lib.a = -2147483649
    lib.b = 525      # try with the first access being in setattr, too
    assert lib.b == 525
    with pytest.raises(AttributeError):
        del lib.a
    with pytest.raises(AttributeError):
        del lib.c
    with pytest.raises(AttributeError):
        del lib.foobarbaz

def test_macro():
    ffi = FFI()
    ffi.cdef("#define FOOBAR ...")
    lib = verify(ffi, 'test_macro', "#define FOOBAR (-6912)")
    assert lib.FOOBAR == -6912
    with pytest.raises(AttributeError):
        lib.FOOBAR = 2

def test_macro_check_value():
    # the value '-0x80000000' in C sources does not have a clear meaning
    # to me; it appears to have a different effect than '-2147483648'...
    # Moreover, on 32-bits, -2147483648 is actually equal to
    # -2147483648U, which in turn is equal to 2147483648U and so positive.
    vals = ['42', '-42', '0x80000000', '-2147483648',
            '0', '9223372036854775809ULL',
            '-9223372036854775807LL']
    if sys.maxsize <= 2**32 or sys.platform == 'win32':
        vals.remove('-2147483648')
    ffi = FFI()
    cdef_lines = ['#define FOO_%d_%d %s' % (i, j, vals[i])
                  for i in range(len(vals))
                  for j in range(len(vals))]
    ffi.cdef('\n'.join(cdef_lines))

    verify_lines = ['#define FOO_%d_%d %s' % (i, j, vals[j])  # [j], not [i]
                    for i in range(len(vals))
                    for j in range(len(vals))]
    lib = verify(ffi, 'test_macro_check_value_ok',
                 '\n'.join(verify_lines))
    #
    for j in range(len(vals)):
        c_got = int(vals[j].replace('U', '').replace('L', ''), 0)
        c_compiler_msg = str(c_got)
        if c_got > 0:
            c_compiler_msg += ' (0x%x)' % (c_got,)
        #
        for i in range(len(vals)):
            attrname = 'FOO_%d_%d' % (i, j)
            if i == j:
                x = getattr(lib, attrname)
                assert x == c_got
            else:
                e = pytest.raises(ffi.error, getattr, lib, attrname)
                assert str(e.value) == (
                    "the C compiler says '%s' is equal to "
                    "%s, but the cdef disagrees" % (attrname, c_compiler_msg))

def test_constant():
    ffi = FFI()
    ffi.cdef("static const int FOOBAR;")
    lib = verify(ffi, 'test_constant', "#define FOOBAR (-6912)")
    assert lib.FOOBAR == -6912
    with pytest.raises(AttributeError):
        lib.FOOBAR = 2

def test_check_value_of_static_const():
    ffi = FFI()
    ffi.cdef("static const int FOOBAR = 042;")
    lib = verify(ffi, 'test_check_value_of_static_const',
                 "#define FOOBAR (-6912)")
    e = pytest.raises(ffi.error, getattr, lib, 'FOOBAR')
    assert str(e.value) == (
       "the C compiler says 'FOOBAR' is equal to -6912, but the cdef disagrees")

def test_constant_nonint():
    ffi = FFI()
    ffi.cdef("static const double FOOBAR;")
    lib = verify(ffi, 'test_constant_nonint', "#define FOOBAR (-6912.5)")
    assert lib.FOOBAR == -6912.5
    with pytest.raises(AttributeError):
        lib.FOOBAR = 2

def test_constant_ptr():
    ffi = FFI()
    ffi.cdef("static double *const FOOBAR;")
    lib = verify(ffi, 'test_constant_ptr', "#define FOOBAR NULL")
    assert lib.FOOBAR == ffi.NULL
    assert ffi.typeof(lib.FOOBAR) == ffi.typeof("double *")

def test_dir():
    ffi = FFI()
    ffi.cdef("int ff(int); extern int aa; static const int my_constant;")
    lib = verify(ffi, 'test_dir', """
        #define my_constant  (-45)
        int aa;
        int ff(int x) { return x+aa; }
    """)
    lib.aa = 5
    assert dir(lib) == ['aa', 'ff', 'my_constant']
    #
    aaobj = lib.__dict__['aa']
    assert not isinstance(aaobj, int)    # some internal object instead
    assert lib.__dict__ == {
        'ff': lib.ff,
        'aa': aaobj,
        'my_constant': -45}
    lib.__dict__['ff'] = "??"
    assert lib.ff(10) == 15

def test_verify_opaque_struct():
    ffi = FFI()
    ffi.cdef("struct foo_s;")
    lib = verify(ffi, 'test_verify_opaque_struct', "struct foo_s;")
    assert ffi.typeof("struct foo_s").cname == "struct foo_s"

def test_verify_opaque_union():
    ffi = FFI()
    ffi.cdef("union foo_s;")
    lib = verify(ffi, 'test_verify_opaque_union', "union foo_s;")
    assert ffi.typeof("union foo_s").cname == "union foo_s"

def test_verify_struct():
    ffi = FFI()
    ffi.cdef("""struct foo_s { int b; short a; ...; };
                struct bar_s { struct foo_s *f; };""")
    lib = verify(ffi, 'test_verify_struct',
                 """struct foo_s { short a; int b; };
                    struct bar_s { struct foo_s *f; };""")
    ffi.typeof("struct bar_s *")
    p = ffi.new("struct foo_s *", {'a': -32768, 'b': -2147483648})
    assert p.a == -32768
    assert p.b == -2147483648
    with pytest.raises(OverflowError):
        p.a -= 1
    with pytest.raises(OverflowError):
        p.b -= 1
    q = ffi.new("struct bar_s *", {'f': p})
    assert q.f == p
    #
    assert ffi.offsetof("struct foo_s", "a") == 0
    assert ffi.offsetof("struct foo_s", "b") == 4
    assert ffi.offsetof(u+"struct foo_s", u+"b") == 4
    #
    pytest.raises(TypeError, ffi.addressof, p)
    assert ffi.addressof(p[0]) == p
    assert ffi.typeof(ffi.addressof(p[0])) is ffi.typeof("struct foo_s *")
    assert ffi.typeof(ffi.addressof(p, "b")) is ffi.typeof("int *")
    assert ffi.addressof(p, "b")[0] == p.b

def test_verify_exact_field_offset():
    ffi = FFI()
    ffi.cdef("""struct foo_s { int b; short a; };""")
    lib = verify(ffi, 'test_verify_exact_field_offset',
                 """struct foo_s { short a; int b; };""")
    e = pytest.raises(ffi.error, ffi.new, "struct foo_s *", [])    # lazily
    assert str(e.value).startswith(
        "struct foo_s: wrong offset for field 'b' (cdef "
        'says 0, but C compiler says 4). fix it or use "...;" ')

def test_type_caching():
    ffi1 = FFI(); ffi1.cdef("struct foo_s;")
    ffi2 = FFI(); ffi2.cdef("struct foo_s;")    # different one!
    lib1 = verify(ffi1, 'test_type_caching_1', 'struct foo_s;')
    lib2 = verify(ffi2, 'test_type_caching_2', 'struct foo_s;')
    # shared types
    assert ffi1.typeof("long") is ffi2.typeof("long")
    assert ffi1.typeof("long**") is ffi2.typeof("long * *")
    assert ffi1.typeof("long(*)(int, ...)") is ffi2.typeof("long(*)(int, ...)")
    # non-shared types
    assert ffi1.typeof("struct foo_s") is not ffi2.typeof("struct foo_s")
    assert ffi1.typeof("struct foo_s *") is not ffi2.typeof("struct foo_s *")
    assert ffi1.typeof("struct foo_s*(*)()") is not (
        ffi2.typeof("struct foo_s*(*)()"))
    assert ffi1.typeof("void(*)(struct foo_s*)") is not (
        ffi2.typeof("void(*)(struct foo_s*)"))

def test_verify_enum():
    ffi = FFI()
    ffi.cdef("""enum e1 { B1, A1, ... }; enum e2 { B2, A2, ... };""")
    lib = verify(ffi, 'test_verify_enum',
                 "enum e1 { A1, B1, C1=%d };" % sys.maxsize +
                 "enum e2 { A2, B2, C2 };")
    ffi.typeof("enum e1")
    ffi.typeof("enum e2")
    assert lib.A1 == 0
    assert lib.B1 == 1
    assert lib.A2 == 0
    assert lib.B2 == 1
    assert ffi.sizeof("enum e1") == ffi.sizeof("long")
    assert ffi.sizeof("enum e2") == ffi.sizeof("int")
    assert repr(ffi.cast("enum e1", 0)) == "<cdata 'enum e1' 0: A1>"

def test_duplicate_enum():
    ffi = FFI()
    ffi.cdef("enum e1 { A1, ... }; enum e2 { A1, ... };")
    pytest.raises(VerificationError, verify, ffi, 'test_duplicate_enum',
                    "enum e1 { A1 }; enum e2 { B1 };")

def test_dotdotdot_length_of_array_field():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a[...]; int b[...]; };")
    verify(ffi, 'test_dotdotdot_length_of_array_field',
           "struct foo_s { int a[42]; int b[11]; };")
    assert ffi.sizeof("struct foo_s") == (42 + 11) * 4
    p = ffi.new("struct foo_s *")
    assert p.a[41] == p.b[10] == 0
    with pytest.raises(IndexError):
        p.a[42]
    with pytest.raises(IndexError):
        p.b[11]

def test_dotdotdot_global_array():
    ffi = FFI()
    ffi.cdef("extern int aa[...]; extern int bb[...];")
    lib = verify(ffi, 'test_dotdotdot_global_array',
                 "int aa[41]; int bb[12];")
    assert ffi.sizeof(lib.aa) == 41 * 4
    assert ffi.sizeof(lib.bb) == 12 * 4
    assert lib.aa[40] == lib.bb[11] == 0
    with pytest.raises(IndexError):
        lib.aa[41]
    with pytest.raises(IndexError):
        lib.bb[12]

def test_misdeclared_field_1():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a[5]; };")
    try:
        verify(ffi, 'test_misdeclared_field_1',
               "struct foo_s { int a[6]; };")
    except VerificationError:
        pass    # ok, fail during compilation already (e.g. C++)
    else:
        assert ffi.sizeof("struct foo_s") == 24  # found by the actual C code
        try:
            # lazily build the fields and boom:
            p = ffi.new("struct foo_s *")
            p.a
            assert False, "should have raised"
        except ffi.error as e:
            assert str(e).startswith("struct foo_s: wrong size for field 'a' "
                                     "(cdef says 20, but C compiler says 24)")

def test_open_array_in_struct():
    ffi = FFI()
    ffi.cdef("struct foo_s { int b; int a[]; };")
    verify(ffi, 'test_open_array_in_struct',
           "struct foo_s { int b; int a[]; };")
    assert ffi.sizeof("struct foo_s") == 4
    p = ffi.new("struct foo_s *", [5, [10, 20, 30, 40]])
    assert p.a[2] == 30
    assert ffi.sizeof(p) == ffi.sizeof("void *")
    assert ffi.sizeof(p[0]) == 5 * ffi.sizeof("int")

def test_math_sin_type():
    ffi = FFI()
    ffi.cdef("double sin(double); void *xxtestfunc();")
    lib = verify(ffi, 'test_math_sin_type', """
        #include <math.h>
        void *xxtestfunc(void) { return 0; }
    """)
    # 'lib.sin' is typed as a <built-in method> object on lib
    assert ffi.typeof(lib.sin).cname == "double(*)(double)"
    # 'x' is another <built-in method> object on lib, made very indirectly
    x = type(lib).__dir__.__get__(lib)
    pytest.raises(TypeError, ffi.typeof, x)
    #
    # present on built-in functions on CPython; must be emulated on PyPy:
    assert lib.sin.__name__ == 'sin'
    assert lib.sin.__module__ == '_CFFI_test_math_sin_type'
    assert lib.sin.__doc__ == (
        "double sin(double);\n"
        "\n"
        "CFFI C function from _CFFI_test_math_sin_type.lib")

    assert ffi.typeof(lib.xxtestfunc).cname == "void *(*)()"
    assert lib.xxtestfunc.__doc__ == (
        "void *xxtestfunc();\n"
        "\n"
        "CFFI C function from _CFFI_test_math_sin_type.lib")

def test_verify_anonymous_struct_with_typedef():
    ffi = FFI()
    ffi.cdef("typedef struct { int a; long b; ...; } foo_t;")
    verify(ffi, 'test_verify_anonymous_struct_with_typedef',
           "typedef struct { long b; int hidden, a; } foo_t;")
    p = ffi.new("foo_t *", {'b': 42})
    assert p.b == 42
    assert repr(p).startswith("<cdata 'foo_t *' ")

def test_verify_anonymous_struct_with_star_typedef():
    ffi = FFI()
    ffi.cdef("typedef struct { int a; long b; } *foo_t;")
    verify(ffi, 'test_verify_anonymous_struct_with_star_typedef',
           "typedef struct { int a; long b; } *foo_t;")
    p = ffi.new("foo_t", {'b': 42})
    assert p.b == 42

def test_verify_anonymous_enum_with_typedef():
    ffi = FFI()
    ffi.cdef("typedef enum { AA, ... } e1;")
    lib = verify(ffi, 'test_verify_anonymous_enum_with_typedef1',
                 "typedef enum { BB, CC, AA } e1;")
    assert lib.AA == 2
    assert ffi.sizeof("e1") == ffi.sizeof("int")
    assert repr(ffi.cast("e1", 2)) == "<cdata 'e1' 2: AA>"
    #
    ffi = FFI()
    ffi.cdef("typedef enum { AA=%d } e1;" % sys.maxsize)
    lib = verify(ffi, 'test_verify_anonymous_enum_with_typedef2',
                 "typedef enum { AA=%d } e1;" % sys.maxsize)
    assert lib.AA == int(ffi.cast("long", sys.maxsize))
    assert ffi.sizeof("e1") == ffi.sizeof("long")

def test_unique_types():
    CDEF = "struct foo_s; union foo_u; enum foo_e { AA };"
    ffi1 = FFI(); ffi1.cdef(CDEF); verify(ffi1, "test_unique_types_1", CDEF)
    ffi2 = FFI(); ffi2.cdef(CDEF); verify(ffi2, "test_unique_types_2", CDEF)
    #
    assert ffi1.typeof("char") is ffi2.typeof("char ")
    assert ffi1.typeof("long") is ffi2.typeof("signed long int")
    assert ffi1.typeof("double *") is ffi2.typeof("double*")
    assert ffi1.typeof("int ***") is ffi2.typeof(" int * * *")
    assert ffi1.typeof("int[]") is ffi2.typeof("signed int[]")
    assert ffi1.typeof("signed int*[17]") is ffi2.typeof("int *[17]")
    assert ffi1.typeof("void") is ffi2.typeof("void")
    assert ffi1.typeof("int(*)(int,int)") is ffi2.typeof("int(*)(int,int)")
    #
    # these depend on user-defined data, so should not be shared
    for name in ["struct foo_s",
                 "union foo_u *",
                 "enum foo_e",
                 "struct foo_s *(*)()",
                 "void(*)(struct foo_s *)",
                 "struct foo_s *(*[5])[8]",
                 ]:
        assert ffi1.typeof(name) is not ffi2.typeof(name)
    # sanity check: twice 'ffi1'
    assert ffi1.typeof("struct foo_s*") is ffi1.typeof("struct foo_s *")

def test_module_name_in_package():
    ffi = FFI()
    ffi.cdef("int foo(int);")
    recompiler.recompile(ffi, "test_module_name_in_package.mymod",
                         "int foo(int x) { return x + 32; }",
                         tmpdir=str(udir))
    old_sys_path = sys.path[:]
    try:
        package_dir = udir.join('test_module_name_in_package')
        for name in os.listdir(str(udir)):
            assert not name.startswith('test_module_name_in_package.')
        assert os.path.isdir(str(package_dir))
        assert len(os.listdir(str(package_dir))) > 0
        assert os.path.exists(str(package_dir.join('mymod.c')))
        package_dir.join('__init__.py').write('')
        #
        getattr(importlib, 'invalidate_caches', object)()
        #
        sys.path.insert(0, str(udir))
        import test_module_name_in_package.mymod
        assert test_module_name_in_package.mymod.lib.foo(10) == 42
        assert test_module_name_in_package.mymod.__name__ == (
            'test_module_name_in_package.mymod')
    finally:
        sys.path[:] = old_sys_path

def test_bad_size_of_global_1():
    ffi = FFI()
    ffi.cdef("extern short glob;")
    pytest.raises(VerificationError, verify, ffi,
                   "test_bad_size_of_global_1", "long glob;")

def test_bad_size_of_global_2():
    ffi = FFI()
    ffi.cdef("extern int glob[10];")
    pytest.raises(VerificationError, verify, ffi,
                   "test_bad_size_of_global_2", "int glob[9];")

def test_unspecified_size_of_global_1():
    ffi = FFI()
    ffi.cdef("extern int glob[];")
    lib = verify(ffi, "test_unspecified_size_of_global_1", "int glob[10];")
    assert ffi.typeof(lib.glob) == ffi.typeof("int *")

def test_unspecified_size_of_global_2():
    ffi = FFI()
    ffi.cdef("extern int glob[][5];")
    lib = verify(ffi, "test_unspecified_size_of_global_2", "int glob[10][5];")
    assert ffi.typeof(lib.glob) == ffi.typeof("int(*)[5]")

def test_unspecified_size_of_global_3():
    ffi = FFI()
    ffi.cdef("extern int glob[][...];")
    lib = verify(ffi, "test_unspecified_size_of_global_3", "int glob[10][5];")
    assert ffi.typeof(lib.glob) == ffi.typeof("int(*)[5]")

def test_unspecified_size_of_global_4():
    ffi = FFI()
    ffi.cdef("extern int glob[...][...];")
    lib = verify(ffi, "test_unspecified_size_of_global_4", "int glob[10][5];")
    assert ffi.typeof(lib.glob) == ffi.typeof("int[10][5]")

def test_include_1():
    ffi1 = FFI()
    ffi1.cdef("typedef double foo_t;")
    verify(ffi1, "test_include_1_parent", "typedef double foo_t;")
    ffi = FFI()
    ffi.include(ffi1)
    ffi.cdef("foo_t ff1(foo_t);")
    lib = verify(ffi, "test_include_1", "double ff1(double x) { return 42.5; }")
    assert lib.ff1(0) == 42.5
    assert ffi1.typeof("foo_t") is ffi.typeof("foo_t") is ffi.typeof("double")

def test_include_1b():
    ffi1 = FFI()
    ffi1.cdef("int foo1(int);")
    lib1 = verify(ffi1, "test_include_1b_parent",
                  "int foo1(int x) { return x + 10; }")
    ffi = FFI()
    ffi.include(ffi1)
    ffi.cdef("int foo2(int);")
    lib = verify(ffi, "test_include_1b", "int foo2(int x) { return x - 5; }")
    assert lib.foo2(42) == 37
    assert lib.foo1(42) == 52
    assert lib.foo1 is lib1.foo1

def test_include_2():
    ffi1 = FFI()
    ffi1.cdef("struct foo_s { int x, y; };")
    verify(ffi1, "test_include_2_parent", "struct foo_s { int x, y; };")
    ffi = FFI()
    ffi.include(ffi1)
    ffi.cdef("struct foo_s *ff2(struct foo_s *);")
    lib = verify(ffi, "test_include_2",
                 "struct foo_s { int x, y; }; //usually from a #include\n"
                 "struct foo_s *ff2(struct foo_s *p) { p->y++; return p; }")
    p = ffi.new("struct foo_s *")
    p.y = 41
    q = lib.ff2(p)
    assert q == p
    assert p.y == 42
    assert ffi1.typeof("struct foo_s") is ffi.typeof("struct foo_s")

def test_include_3():
    ffi1 = FFI()
    ffi1.cdef("typedef short sshort_t;")
    verify(ffi1, "test_include_3_parent", "typedef short sshort_t;")
    ffi = FFI()
    ffi.include(ffi1)
    ffi.cdef("sshort_t ff3(sshort_t);")
    lib = verify(ffi, "test_include_3",
                 "typedef short sshort_t; //usually from a #include\n"
                 "sshort_t ff3(sshort_t x) { return (sshort_t)(x + 42); }")
    assert lib.ff3(10) == 52
    assert ffi.typeof(ffi.cast("sshort_t", 42)) is ffi.typeof("short")
    assert ffi1.typeof("sshort_t") is ffi.typeof("sshort_t")

def test_include_4():
    ffi1 = FFI()
    ffi1.cdef("typedef struct { int x; } mystruct_t;")
    verify(ffi1, "test_include_4_parent",
           "typedef struct { int x; } mystruct_t;")
    ffi = FFI()
    ffi.include(ffi1)
    ffi.cdef("mystruct_t *ff4(mystruct_t *);")
    lib = verify(ffi, "test_include_4",
           "typedef struct {int x; } mystruct_t; //usually from a #include\n"
           "mystruct_t *ff4(mystruct_t *p) { p->x += 42; return p; }")
    p = ffi.new("mystruct_t *", [10])
    q = lib.ff4(p)
    assert q == p
    assert p.x == 52
    assert ffi1.typeof("mystruct_t") is ffi.typeof("mystruct_t")

def test_include_5():
    ffi1 = FFI()
    ffi1.cdef("typedef struct { int x[2]; int y; } *mystruct_p;")
    verify(ffi1, "test_include_5_parent",
           "typedef struct { int x[2]; int y; } *mystruct_p;")
    ffi = FFI()
    ffi.include(ffi1)
    ffi.cdef("mystruct_p ff5(mystruct_p);")
    lib = verify(ffi, "test_include_5",
        "typedef struct {int x[2]; int y; } *mystruct_p; //usually #include\n"
        "mystruct_p ff5(mystruct_p p) { p->x[1] += 42; return p; }")
    assert ffi.alignof(ffi.typeof("mystruct_p").item) == 4
    assert ffi1.typeof("mystruct_p") is ffi.typeof("mystruct_p")
    p = ffi.new("mystruct_p", [[5, 10], -17])
    q = lib.ff5(p)
    assert q == p
    assert p.x[0] == 5
    assert p.x[1] == 52
    assert p.y == -17
    assert ffi.alignof(ffi.typeof(p[0])) == 4

def test_include_6():
    ffi1 = FFI()
    ffi1.cdef("typedef ... mystruct_t;")
    verify(ffi1, "test_include_6_parent",
           "typedef struct _mystruct_s mystruct_t;")
    ffi = FFI()
    ffi.include(ffi1)
    ffi.cdef("mystruct_t *ff6(void); int ff6b(mystruct_t *);")
    lib = verify(ffi, "test_include_6",
           "typedef struct _mystruct_s mystruct_t; //usually from a #include\n"
           "struct _mystruct_s { int x; };\n"
           "static mystruct_t result_struct = { 42 };\n"
           "mystruct_t *ff6(void) { return &result_struct; }\n"
           "int ff6b(mystruct_t *p) { return p->x; }")
    p = lib.ff6()
    assert ffi.cast("int *", p)[0] == 42
    assert lib.ff6b(p) == 42

def test_include_7():
    ffi1 = FFI()
    ffi1.cdef("typedef ... mystruct_t;\n"
              "int ff7b(mystruct_t *);")
    verify(ffi1, "test_include_7_parent",
           "typedef struct { int x; } mystruct_t;\n"
           "int ff7b(mystruct_t *p) { return p->x; }")
    ffi = FFI()
    ffi.include(ffi1)
    ffi.cdef("mystruct_t *ff7(void);")
    lib = verify(ffi, "test_include_7",
           "typedef struct { int x; } mystruct_t; //usually from a #include\n"
           "static mystruct_t result_struct = { 42 };"
           "mystruct_t *ff7(void) { return &result_struct; }")
    p = lib.ff7()
    assert ffi.cast("int *", p)[0] == 42
    assert lib.ff7b(p) == 42

def test_include_8():
    ffi1 = FFI()
    ffi1.cdef("struct foo_s;")
    verify(ffi1, "test_include_8_parent", "struct foo_s;")
    ffi = FFI()
    ffi.include(ffi1)
    ffi.cdef("struct foo_s { int x, y; };")
    verify(ffi, "test_include_8", "struct foo_s { int x, y; };")
    e = pytest.raises(NotImplementedError, ffi.new, "struct foo_s *")
    assert str(e.value) == (
        "'struct foo_s' is opaque in the ffi.include(), but no longer in "
        "the ffi doing the include (workaround: don't use ffi.include() but"
        " duplicate the declarations of everything using struct foo_s)")

def test_unicode_libraries():
    try:
        unicode
    except NameError:
        pytest.skip("for python 2.x")
    #
    import math
    lib_m = "m"
    if sys.platform == 'win32':
        #there is a small chance this fails on Mingw via environ $CC
        import distutils.ccompiler
        if distutils.ccompiler.get_default_compiler() == 'msvc':
            lib_m = 'msvcrt'
    ffi = FFI()
    ffi.cdef(unicode("float sin(double); double cos(double);"))
    lib = verify(ffi, 'test_math_sin_unicode', unicode('#include <math.h>'),
                 libraries=[unicode(lib_m)], ignore_warnings=True)
    assert lib.cos(1.43) == math.cos(1.43)

def test_incomplete_struct_as_arg():
    ffi = FFI()
    ffi.cdef("struct foo_s { int x; ...; }; int f(int, struct foo_s);")
    lib = verify(ffi, "test_incomplete_struct_as_arg",
                 "struct foo_s { int a, x, z; };\n"
                 "int f(int b, struct foo_s s) { return s.x * b; }")
    s = ffi.new("struct foo_s *", [21])
    assert s.x == 21
    assert ffi.sizeof(s[0]) == 12
    assert ffi.offsetof(ffi.typeof(s), 'x') == 4
    assert lib.f(2, s[0]) == 42
    assert ffi.typeof(lib.f) == ffi.typeof("int(*)(int, struct foo_s)")

def test_incomplete_struct_as_result():
    ffi = FFI()
    ffi.cdef("struct foo_s { int x; ...; }; struct foo_s f(int);")
    lib = verify(ffi, "test_incomplete_struct_as_result",
            "struct foo_s { int a, x, z; };\n"
            "struct foo_s f(int x) { struct foo_s r; r.x = x * 2; return r; }")
    s = lib.f(21)
    assert s.x == 42
    assert ffi.typeof(lib.f) == ffi.typeof("struct foo_s(*)(int)")

def test_incomplete_struct_as_both():
    ffi = FFI()
    ffi.cdef("struct foo_s { int x; ...; }; struct bar_s { int y; ...; };\n"
             "struct foo_s f(int, struct bar_s);")
    lib = verify(ffi, "test_incomplete_struct_as_both",
            "struct foo_s { int a, x, z; };\n"
            "struct bar_s { int b, c, y, d; };\n"
            "struct foo_s f(int x, struct bar_s b) {\n"
            "  struct foo_s r; r.x = x * b.y; return r;\n"
            "}")
    b = ffi.new("struct bar_s *", [7])
    s = lib.f(6, b[0])
    assert s.x == 42
    assert ffi.typeof(lib.f) == ffi.typeof(
        "struct foo_s(*)(int, struct bar_s)")
    s = lib.f(14, {'y': -3})
    assert s.x == -42

def test_name_of_unnamed_struct():
    ffi = FFI()
    ffi.cdef("typedef struct { int x; } foo_t;\n"
             "typedef struct { int y; } *bar_p;\n"
             "typedef struct { int y; } **baz_pp;\n")
    verify(ffi, "test_name_of_unnamed_struct",
             "typedef struct { int x; } foo_t;\n"
             "typedef struct { int y; } *bar_p;\n"
             "typedef struct { int y; } **baz_pp;\n")
    assert repr(ffi.typeof("foo_t")) == "<ctype 'foo_t'>"
    assert repr(ffi.typeof("bar_p")) == "<ctype 'struct $1 *'>"
    assert repr(ffi.typeof("baz_pp")) == "<ctype 'struct $2 * *'>"

def test_address_of_global_var():
    ffi = FFI()
    ffi.cdef("""
        extern long bottom, bottoms[2];
        long FetchRectBottom(void);
        long FetchRectBottoms1(void);
        #define FOOBAR 42
    """)
    lib = verify(ffi, "test_address_of_global_var", """
        long bottom, bottoms[2];
        long FetchRectBottom(void) { return bottom; }
        long FetchRectBottoms1(void) { return bottoms[1]; }
        #define FOOBAR 42
    """)
    lib.bottom = 300
    assert lib.FetchRectBottom() == 300
    lib.bottom += 1
    assert lib.FetchRectBottom() == 301
    lib.bottoms[1] = 500
    assert lib.FetchRectBottoms1() == 500
    lib.bottoms[1] += 2
    assert lib.FetchRectBottoms1() == 502
    #
    p = ffi.addressof(lib, 'bottom')
    assert ffi.typeof(p) == ffi.typeof("long *")
    assert p[0] == 301
    p[0] += 1
    assert lib.FetchRectBottom() == 302
    p = ffi.addressof(lib, 'bottoms')
    assert ffi.typeof(p) == ffi.typeof("long(*)[2]")
    assert p[0] == lib.bottoms
    #
    pytest.raises(AttributeError, ffi.addressof, lib, 'unknown_var')
    pytest.raises(AttributeError, ffi.addressof, lib, "FOOBAR")

def test_defines__CFFI_():
    # Check that we define the macro _CFFI_ automatically.
    # It should be done before including Python.h, so that PyPy's Python.h
    # can check for it.
    ffi = FFI()
    ffi.cdef("""
        #define CORRECT 1
    """)
    lib = verify(ffi, "test_defines__CFFI_", """
    #ifdef _CFFI_
    #    define CORRECT 1
    #endif
    """)
    assert lib.CORRECT == 1

def test_unpack_args():
    ffi = FFI()
    ffi.cdef("void foo0(void); void foo1(int); void foo2(int, int);")
    lib = verify(ffi, "test_unpack_args", """
    void foo0(void) { }
    void foo1(int x) { }
    void foo2(int x, int y) { }
    """)
    assert 'foo0' in repr(lib.foo0)
    assert 'foo1' in repr(lib.foo1)
    assert 'foo2' in repr(lib.foo2)
    lib.foo0()
    lib.foo1(42)
    lib.foo2(43, 44)
    e1 = pytest.raises(TypeError, lib.foo0, 42)
    e2 = pytest.raises(TypeError, lib.foo0, 43, 44)
    e3 = pytest.raises(TypeError, lib.foo1)
    e4 = pytest.raises(TypeError, lib.foo1, 43, 44)
    e5 = pytest.raises(TypeError, lib.foo2)
    e6 = pytest.raises(TypeError, lib.foo2, 42)
    e7 = pytest.raises(TypeError, lib.foo2, 45, 46, 47)
    def st1(s):
        s = str(s)
        if s.startswith("_CFFI_test_unpack_args.Lib."):
            s = s[len("_CFFI_test_unpack_args.Lib."):]
        return s
    assert st1(e1.value) == "foo0() takes no arguments (1 given)"
    assert st1(e2.value) == "foo0() takes no arguments (2 given)"
    assert st1(e3.value) == "foo1() takes exactly one argument (0 given)"
    assert st1(e4.value) == "foo1() takes exactly one argument (2 given)"
    assert st1(e5.value) in ["foo2 expected 2 arguments, got 0",
                             "foo2() takes exactly 2 arguments (0 given)"]
    assert st1(e6.value) in ["foo2 expected 2 arguments, got 1",
                             "foo2() takes exactly 2 arguments (1 given)"]
    assert st1(e7.value) in ["foo2 expected 2 arguments, got 3",
                             "foo2() takes exactly 2 arguments (3 given)"]

def test_address_of_function():
    ffi = FFI()
    ffi.cdef("long myfunc(long x);")
    lib = verify(ffi, "test_addressof_function", """
        char myfunc(char x) { return (char)(x + 42); }
    """, ignore_warnings=True)
    assert lib.myfunc(5) == 47
    assert lib.myfunc(0xABC05) == 47
    assert not isinstance(lib.myfunc, ffi.CData)
    assert ffi.typeof(lib.myfunc) == ffi.typeof("long(*)(long)")
    addr = ffi.addressof(lib, 'myfunc')
    assert addr(5) == 47
    assert addr(0xABC05) == 47
    assert isinstance(addr, ffi.CData)
    assert ffi.typeof(addr) == ffi.typeof("long(*)(long)")

def test_address_of_function_with_struct():
    ffi = FFI()
    ffi.cdef("struct foo_s { int x; }; long myfunc(struct foo_s);")
    lib = verify(ffi, "test_addressof_function_with_struct", """
        struct foo_s { int x; };
        char myfunc(struct foo_s input) { return (char)(input.x + 42); }
    """)
    s = ffi.new("struct foo_s *", [5])[0]
    assert lib.myfunc(s) == 47
    assert not isinstance(lib.myfunc, ffi.CData)
    assert ffi.typeof(lib.myfunc) == ffi.typeof("long(*)(struct foo_s)")
    addr = ffi.addressof(lib, 'myfunc')
    assert addr(s) == 47
    assert isinstance(addr, ffi.CData)
    assert ffi.typeof(addr) == ffi.typeof("long(*)(struct foo_s)")

def test_issue198():
    ffi = FFI()
    ffi.cdef("""
        typedef struct{...;} opaque_t;
        const opaque_t CONSTANT;
        int toint(opaque_t);
    """)
    lib = verify(ffi, 'test_issue198', """
        typedef int opaque_t;
        #define CONSTANT ((opaque_t)42)
        static int toint(opaque_t o) { return o; }
    """)
    def random_stuff():
        pass
    assert lib.toint(lib.CONSTANT) == 42
    random_stuff()
    assert lib.toint(lib.CONSTANT) == 42

def test_constant_is_not_a_compiler_constant():
    ffi = FFI()
    ffi.cdef("static const float almost_forty_two;")
    lib = verify(ffi, 'test_constant_is_not_a_compiler_constant', """
        static float f(void) { return 42.25; }
        #define almost_forty_two (f())
    """)
    assert lib.almost_forty_two == 42.25

def test_constant_of_unknown_size():
    ffi = FFI()
    ffi.cdef("""
        typedef ... opaque_t;
        const opaque_t CONSTANT;
    """)
    lib = verify(ffi, 'test_constant_of_unknown_size',
                 "typedef int opaque_t;"
                 "const int CONSTANT = 42;")
    e = pytest.raises(ffi.error, getattr, lib, 'CONSTANT')
    assert str(e.value) == ("constant 'CONSTANT' is of "
                            "type 'opaque_t', whose size is not known")

def test_variable_of_unknown_size():
    ffi = FFI()
    ffi.cdef("""
        typedef ... opaque_t;
        extern opaque_t globvar;
    """)
    lib = verify(ffi, 'test_variable_of_unknown_size', """
        typedef char opaque_t[6];
        opaque_t globvar = "hello";
    """)
    # can't read or write it at all
    e = pytest.raises(TypeError, getattr, lib, 'globvar')
    assert str(e.value) in ["cdata 'opaque_t' is opaque",
                            "'opaque_t' is opaque or not completed yet"] #pypy
    e = pytest.raises(TypeError, setattr, lib, 'globvar', [])
    assert str(e.value) in ["'opaque_t' is opaque",
                            "'opaque_t' is opaque or not completed yet"] #pypy
    # but we can get its address
    p = ffi.addressof(lib, 'globvar')
    assert ffi.typeof(p) == ffi.typeof('opaque_t *')
    assert ffi.string(ffi.cast("char *", p), 8) == b"hello"

def test_constant_of_value_unknown_to_the_compiler():
    extra_c_source = udir.join(
        'extra_test_constant_of_value_unknown_to_the_compiler.c')
    extra_c_source.write('const int external_foo = 42;\n')
    ffi = FFI()
    ffi.cdef("const int external_foo;")
    lib = verify(ffi, 'test_constant_of_value_unknown_to_the_compiler', """
        extern const int external_foo;
    """, sources=[str(extra_c_source)])
    assert lib.external_foo == 42

def test_dotdot_in_source_file_names():
    extra_c_source = udir.join(
        'extra_test_dotdot_in_source_file_names.c')
    extra_c_source.write('const int external_foo = 42;\n')
    ffi = FFI()
    ffi.cdef("const int external_foo;")
    lib = verify(ffi, 'test_dotdot_in_source_file_names', """
        extern const int external_foo;
    """, sources=[os.path.join(os.path.dirname(str(extra_c_source)),
                               'foobar', '..',
                               os.path.basename(str(extra_c_source)))])
    assert lib.external_foo == 42

def test_call_with_incomplete_structs():
    ffi = FFI()
    ffi.cdef("typedef struct {...;} foo_t; "
             "extern foo_t myglob; "
             "foo_t increment(foo_t s); "
             "double getx(foo_t s);")
    lib = verify(ffi, 'test_call_with_incomplete_structs', """
        typedef double foo_t;
        double myglob = 42.5;
        double getx(double x) { return x; }
        double increment(double x) { return x + 1; }
    """)
    assert lib.getx(lib.myglob) == 42.5
    assert lib.getx(lib.increment(lib.myglob)) == 43.5

def test_struct_array_guess_length_2():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a[...][...]; };")
    lib = verify(ffi, 'test_struct_array_guess_length_2',
                 "struct foo_s { int x; int a[5][8]; int y; };")
    assert ffi.sizeof('struct foo_s') == 42 * ffi.sizeof('int')
    s = ffi.new("struct foo_s *")
    assert ffi.typeof(s.a) == ffi.typeof("int[5][8]")
    assert ffi.sizeof(s.a) == 40 * ffi.sizeof('int')
    assert s.a[4][7] == 0
    with pytest.raises(IndexError):
        s.a[4][8]
    with pytest.raises(IndexError):
        s.a[5][0]
    assert ffi.typeof(s.a) == ffi.typeof("int[5][8]")
    assert ffi.typeof(s.a[0]) == ffi.typeof("int[8]")

def test_struct_array_guess_length_3():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a[][...]; };")
    lib = verify(ffi, 'test_struct_array_guess_length_3',
                 "struct foo_s { int x; int a[5][7]; int y; };")
    assert ffi.sizeof('struct foo_s') == 37 * ffi.sizeof('int')
    s = ffi.new("struct foo_s *")
    assert ffi.typeof(s.a) == ffi.typeof("int[][7]")
    assert s.a[4][6] == 0
    with pytest.raises(IndexError):
        s.a[4][7]
    assert ffi.typeof(s.a[0]) == ffi.typeof("int[7]")

def test_global_var_array_2():
    ffi = FFI()
    ffi.cdef("extern int a[...][...];")
    lib = verify(ffi, 'test_global_var_array_2', 'int a[10][8];')
    lib.a[9][7] = 123456
    assert lib.a[9][7] == 123456
    with pytest.raises(IndexError):
        lib.a[0][8]
    with pytest.raises(IndexError):
        lib.a[10][0]
    assert ffi.typeof(lib.a) == ffi.typeof("int[10][8]")
    assert ffi.typeof(lib.a[0]) == ffi.typeof("int[8]")

def test_global_var_array_3():
    ffi = FFI()
    ffi.cdef("extern int a[][...];")
    lib = verify(ffi, 'test_global_var_array_3', 'int a[10][8];')
    lib.a[9][7] = 123456
    assert lib.a[9][7] == 123456
    with pytest.raises(IndexError):
        lib.a[0][8]
    assert ffi.typeof(lib.a) == ffi.typeof("int(*)[8]")
    assert ffi.typeof(lib.a[0]) == ffi.typeof("int[8]")

def test_global_var_array_4():
    ffi = FFI()
    ffi.cdef("extern int a[10][...];")
    lib = verify(ffi, 'test_global_var_array_4', 'int a[10][8];')
    lib.a[9][7] = 123456
    assert lib.a[9][7] == 123456
    with pytest.raises(IndexError):
        lib.a[0][8]
    with pytest.raises(IndexError):
        lib.a[10][8]
    assert ffi.typeof(lib.a) == ffi.typeof("int[10][8]")
    assert ffi.typeof(lib.a[0]) == ffi.typeof("int[8]")

def test_some_integer_type():
    ffi = FFI()
    ffi.cdef("""
        typedef int... foo_t;
        typedef unsigned long... bar_t;
        typedef struct { foo_t a, b; } mystruct_t;
        foo_t foobar(bar_t, mystruct_t);
        static const bar_t mu = -20;
        static const foo_t nu = 20;
    """)
    lib = verify(ffi, 'test_some_integer_type', """
        typedef unsigned long long foo_t;
        typedef short bar_t;
        typedef struct { foo_t a, b; } mystruct_t;
        static foo_t foobar(bar_t x, mystruct_t s) {
            return (foo_t)x + s.a + s.b;
        }
        static const bar_t mu = -20;
        static const foo_t nu = 20;
    """)
    assert ffi.sizeof("foo_t") == ffi.sizeof("unsigned long long")
    assert ffi.sizeof("bar_t") == ffi.sizeof("short")
    maxulonglong = 2 ** 64 - 1
    assert int(ffi.cast("foo_t", -1)) == maxulonglong
    assert int(ffi.cast("bar_t", -1)) == -1
    assert lib.foobar(-1, [0, 0]) == maxulonglong
    assert lib.foobar(2 ** 15 - 1, [0, 0]) == 2 ** 15 - 1
    assert lib.foobar(10, [20, 31]) == 61
    assert lib.foobar(0, [0, maxulonglong]) == maxulonglong
    pytest.raises(OverflowError, lib.foobar, 2 ** 15, [0, 0])
    pytest.raises(OverflowError, lib.foobar, -(2 ** 15) - 1, [0, 0])
    pytest.raises(OverflowError, ffi.new, "mystruct_t *", [0, -1])
    assert lib.mu == -20
    assert lib.nu == 20

def test_some_float_type():
    ffi = FFI()
    ffi.cdef("""
        typedef double... foo_t;
        typedef float... bar_t;
        foo_t sum(foo_t[]);
        bar_t neg(bar_t);
        """)
    lib = verify(ffi, 'test_some_float_type', """
        typedef float foo_t;
        static foo_t sum(foo_t x[]) { return x[0] + x[1]; }
        typedef double bar_t;
        static double neg(double x) { return -x; }
    """)
    assert lib.sum([40.0, 2.25]) == 42.25
    assert lib.sum([12.3, 45.6]) != 12.3 + 45.6     # precision loss
    assert lib.neg(12.3) == -12.3                   # no precision loss
    assert ffi.sizeof("foo_t") == ffi.sizeof("float")
    assert ffi.sizeof("bar_t") == ffi.sizeof("double")

def test_some_float_invalid_1():
    ffi = FFI()
    pytest.raises((FFIError,      # with pycparser <= 2.17
                    CDefError),    # with pycparser >= 2.18
                   ffi.cdef, "typedef long double... foo_t;")

def test_some_float_invalid_2():
    ffi = FFI()
    ffi.cdef("typedef double... foo_t; foo_t neg(foo_t);")
    lib = verify(ffi, 'test_some_float_invalid_2', """
        typedef unsigned long foo_t;
        foo_t neg(foo_t x) { return -x; }
    """)
    e = pytest.raises(ffi.error, getattr, lib, 'neg')
    assert str(e.value) == ("primitive floating-point type with an unexpected "
                            "size (or not a float type at all)")

def test_some_float_invalid_3():
    ffi = FFI()
    ffi.cdef("typedef double... foo_t; foo_t neg(foo_t);")
    lib = verify(ffi, 'test_some_float_invalid_3', """
        typedef long double foo_t;
        foo_t neg(foo_t x) { return -x; }
    """, ignore_warnings=True)
    if ffi.sizeof("long double") == ffi.sizeof("double"):
        assert lib.neg(12.3) == -12.3
    else:
        e = pytest.raises(ffi.error, getattr, lib, 'neg')
        assert str(e.value) == ("primitive floating-point type is "
                                "'long double', not supported for now with "
                                "the syntax 'typedef double... xxx;'")

def test_issue200():
    ffi = FFI()
    ffi.cdef("""
        typedef void (function_t)(void*);
        void function(void *);
    """)
    lib = verify(ffi, 'test_issue200', """
        static void function(void *p) { (void)p; }
    """)
    ffi.typeof('function_t*')
    lib.function(ffi.NULL)
    # assert did not crash

def test_alignment_of_longlong():
    ffi = FFI()
    x1 = ffi.alignof('unsigned long long')
    assert x1 in [4, 8]
    ffi.cdef("struct foo_s { unsigned long long x; };")
    lib = verify(ffi, 'test_alignment_of_longlong',
                 "struct foo_s { unsigned long long x; };")
    assert ffi.alignof('unsigned long long') == x1
    assert ffi.alignof('struct foo_s') == x1

def test_import_from_lib():
    ffi = FFI()
    ffi.cdef("int mybar(int); static int myvar;\n#define MYFOO ...")
    lib = verify(ffi, 'test_import_from_lib',
                 "#define MYFOO 42\n"
                 "static int mybar(int x) { return x + 1; }\n"
                 "static int myvar = -5;")
    assert sys.modules['_CFFI_test_import_from_lib'].lib is lib
    assert sys.modules['_CFFI_test_import_from_lib.lib'] is lib
    from _CFFI_test_import_from_lib.lib import MYFOO
    assert MYFOO == 42
    assert hasattr(lib, '__dict__')
    assert lib.__all__ == ['MYFOO', 'mybar']   # but not 'myvar'
    assert lib.__name__ == '_CFFI_test_import_from_lib.lib'
    assert lib.__class__ is type(sys)   # !! hack for help()

def test_macro_var_callback():
    ffi = FFI()
    ffi.cdef("extern int my_value; extern int *(*get_my_value)(void);")
    lib = verify(ffi, 'test_macro_var_callback',
                 "int *(*get_my_value)(void);\n"
                 "#define my_value (*get_my_value())")
    #
    values = ffi.new("int[50]")
    def it():
        for i in range(50):
            yield i
    it = it()
    #
    @ffi.callback("int *(*)(void)")
    def get_my_value():
        for nextvalue in it:
            return values + nextvalue
    lib.get_my_value = get_my_value
    #
    values[0] = 41
    assert lib.my_value == 41            # [0]
    p = ffi.addressof(lib, 'my_value')   # [1]
    assert p == values + 1
    assert p[-1] == 41
    assert p[+1] == 0
    lib.my_value = 42                    # [2]
    assert values[2] == 42
    assert p[-1] == 41
    assert p[+1] == 42
    #
    # if get_my_value raises or returns nonsense, the exception is printed
    # to stderr like with any callback, but then the C expression 'my_value'
    # expand to '*NULL'.  We assume here that '&my_value' will return NULL
    # without segfaulting, and check for NULL when accessing the variable.
    @ffi.callback("int *(*)(void)")
    def get_my_value():
        raise LookupError
    lib.get_my_value = get_my_value
    pytest.raises(ffi.error, getattr, lib, 'my_value')
    pytest.raises(ffi.error, setattr, lib, 'my_value', 50)
    pytest.raises(ffi.error, ffi.addressof, lib, 'my_value')
    @ffi.callback("int *(*)(void)")
    def get_my_value():
        return "hello"
    lib.get_my_value = get_my_value
    pytest.raises(ffi.error, getattr, lib, 'my_value')
    e = pytest.raises(ffi.error, setattr, lib, 'my_value', 50)
    assert str(e.value) == "global variable 'my_value' is at address NULL"

def test_const_fields():
    ffi = FFI()
    ffi.cdef("""struct foo_s { const int a; void *const b; };""")
    lib = verify(ffi, 'test_const_fields', """
        struct foo_s { const int a; void *const b; };""")
    foo_s = ffi.typeof("struct foo_s")
    assert foo_s.fields[0][0] == 'a'
    assert foo_s.fields[0][1].type is ffi.typeof("int")
    assert foo_s.fields[1][0] == 'b'
    assert foo_s.fields[1][1].type is ffi.typeof("void *")

def test_restrict_fields():
    ffi = FFI()
    ffi.cdef("""struct foo_s { void * restrict b; };""")
    lib = verify(ffi, 'test_restrict_fields', """
        struct foo_s { void * __restrict b; };""")
    foo_s = ffi.typeof("struct foo_s")
    assert foo_s.fields[0][0] == 'b'
    assert foo_s.fields[0][1].type is ffi.typeof("void *")

def test_volatile_fields():
    ffi = FFI()
    ffi.cdef("""struct foo_s { void * volatile b; };""")
    lib = verify(ffi, 'test_volatile_fields', """
        struct foo_s { void * volatile b; };""")
    foo_s = ffi.typeof("struct foo_s")
    assert foo_s.fields[0][0] == 'b'
    assert foo_s.fields[0][1].type is ffi.typeof("void *")

def test_const_array_fields():
    ffi = FFI()
    ffi.cdef("""struct foo_s { const int a[4]; };""")
    lib = verify(ffi, 'test_const_array_fields', """
        struct foo_s { const int a[4]; };""")
    foo_s = ffi.typeof("struct foo_s")
    assert foo_s.fields[0][0] == 'a'
    assert foo_s.fields[0][1].type is ffi.typeof("int[4]")

def test_const_array_fields_varlength():
    ffi = FFI()
    ffi.cdef("""struct foo_s { const int a[]; ...; };""")
    lib = verify(ffi, 'test_const_array_fields_varlength', """
        struct foo_s { const int a[4]; };""")
    foo_s = ffi.typeof("struct foo_s")
    assert foo_s.fields[0][0] == 'a'
    assert foo_s.fields[0][1].type is ffi.typeof("int[]")

def test_const_array_fields_unknownlength():
    ffi = FFI()
    ffi.cdef("""struct foo_s { const int a[...]; ...; };""")
    lib = verify(ffi, 'test_const_array_fields_unknownlength', """
        struct foo_s { const int a[4]; };""")
    foo_s = ffi.typeof("struct foo_s")
    assert foo_s.fields[0][0] == 'a'
    assert foo_s.fields[0][1].type is ffi.typeof("int[4]")

def test_const_function_args():
    ffi = FFI()
    ffi.cdef("""int foobar(const int a, const int *b, const int c[]);""")
    lib = verify(ffi, 'test_const_function_args', """
        int foobar(const int a, const int *b, const int c[]) {
            return a + *b + *c;
        }
    """)
    assert lib.foobar(100, ffi.new("int *", 40), ffi.new("int *", 2)) == 142

def test_const_function_type_args():
    ffi = FFI()
    ffi.cdef("""extern int(*foobar)(const int a,const int*b,const int c[]);""")
    lib = verify(ffi, 'test_const_function_type_args', """
        int (*foobar)(const int a, const int *b, const int c[]);
    """)
    t = ffi.typeof(lib.foobar)
    assert t.args[0] is ffi.typeof("int")
    assert t.args[1] is ffi.typeof("int *")
    assert t.args[2] is ffi.typeof("int *")

def test_const_constant():
    ffi = FFI()
    ffi.cdef("""struct foo_s { int x,y; }; const struct foo_s myfoo;""")
    lib = verify(ffi, 'test_const_constant', """
        struct foo_s { int x,y; }; const struct foo_s myfoo = { 40, 2 };
    """)
    assert lib.myfoo.x == 40
    assert lib.myfoo.y == 2

def test_const_via_typedef():
    ffi = FFI()
    ffi.cdef("""typedef const int const_t; const_t aaa;""")
    lib = verify(ffi, 'test_const_via_typedef', """
        typedef const int const_t;
        #define aaa 42
    """)
    assert lib.aaa == 42
    with pytest.raises(AttributeError):
        lib.aaa = 43

def test_win32_calling_convention_0():
    ffi = FFI()
    ffi.cdef("""
        int call1(int(__cdecl   *cb)(int));
        int (*const call2)(int(__stdcall *cb)(int));
    """)
    lib = verify(ffi, 'test_win32_calling_convention_0', r"""
        #ifndef _MSC_VER
        #  define __stdcall  /* nothing */
        #endif
        int call1(int(*cb)(int)) {
            int i, result = 0;
            //printf("call1: cb = %p\n", cb);
            for (i = 0; i < 1000; i++)
                result += cb(i);
            //printf("result = %d\n", result);
            return result;
        }
        int call2(int(__stdcall *cb)(int)) {
            int i, result = 0;
            //printf("call2: cb = %p\n", cb);
            for (i = 0; i < 1000; i++)
                result += cb(-i);
            //printf("result = %d\n", result);
            return result;
        }
    """)
    @ffi.callback("int(int)")
    def cb1(x):
        return x * 2
    @ffi.callback("int __stdcall(int)")
    def cb2(x):
        return x * 3
    res = lib.call1(cb1)
    assert res == 500*999*2
    assert res == ffi.addressof(lib, 'call1')(cb1)
    res = lib.call2(cb2)
    assert res == -500*999*3
    assert res == ffi.addressof(lib, 'call2')(cb2)
    if sys.platform == 'win32' and not sys.maxsize > 2**32:
        assert '__stdcall' in str(ffi.typeof(cb2))
        assert '__stdcall' not in str(ffi.typeof(cb1))
        pytest.raises(TypeError, lib.call1, cb2)
        pytest.raises(TypeError, lib.call2, cb1)
    else:
        assert '__stdcall' not in str(ffi.typeof(cb2))
        assert ffi.typeof(cb2) is ffi.typeof(cb1)

def test_win32_calling_convention_1():
    ffi = FFI()
    ffi.cdef("""
        int __cdecl   call1(int(__cdecl   *cb)(int));
        int __stdcall call2(int(__stdcall *cb)(int));
        int (__cdecl   *const cb1)(int);
        int (__stdcall *const cb2)(int);
    """)
    lib = verify(ffi, 'test_win32_calling_convention_1', r"""
        #ifndef _MSC_VER
        #  define __cdecl
        #  define __stdcall
        #endif
        int __cdecl   cb1(int x) { return x * 2; }
        int __stdcall cb2(int x) { return x * 3; }

        int __cdecl call1(int(__cdecl *cb)(int)) {
            int i, result = 0;
            //printf("here1\n");
            //printf("cb = %p, cb1 = %p\n", cb, (void *)cb1);
            for (i = 0; i < 1000; i++)
                result += cb(i);
            //printf("result = %d\n", result);
            return result;
        }
        int __stdcall call2(int(__stdcall *cb)(int)) {
            int i, result = 0;
            //printf("here1\n");
            //printf("cb = %p, cb2 = %p\n", cb, (void *)cb2);
            for (i = 0; i < 1000; i++)
                result += cb(-i);
            //printf("result = %d\n", result);
            return result;
        }
    """)
    #print '<<< cb1 =', ffi.addressof(lib, 'cb1')
    ptr_call1 = ffi.addressof(lib, 'call1')
    assert lib.call1(ffi.addressof(lib, 'cb1')) == 500*999*2
    assert ptr_call1(ffi.addressof(lib, 'cb1')) == 500*999*2
    #print '<<< cb2 =', ffi.addressof(lib, 'cb2')
    ptr_call2 = ffi.addressof(lib, 'call2')
    assert lib.call2(ffi.addressof(lib, 'cb2')) == -500*999*3
    assert ptr_call2(ffi.addressof(lib, 'cb2')) == -500*999*3
    #print '<<< done'

def test_win32_calling_convention_2():
    # any mistake in the declaration of plain function (including the
    # precise argument types and, here, the calling convention) are
    # automatically corrected.  But this does not apply to the 'cb'
    # function pointer argument.
    ffi = FFI()
    ffi.cdef("""
        int __stdcall call1(int(__cdecl   *cb)(int));
        int __cdecl   call2(int(__stdcall *cb)(int));
        int (__cdecl   *const cb1)(int);
        int (__stdcall *const cb2)(int);
    """)
    lib = verify(ffi, 'test_win32_calling_convention_2', """
        #ifndef _MSC_VER
        #  define __cdecl
        #  define __stdcall
        #endif
        int __cdecl call1(int(__cdecl *cb)(int)) {
            int i, result = 0;
            for (i = 0; i < 1000; i++)
                result += cb(i);
            return result;
        }
        int __stdcall call2(int(__stdcall *cb)(int)) {
            int i, result = 0;
            for (i = 0; i < 1000; i++)
                result += cb(-i);
            return result;
        }
        int __cdecl   cb1(int x) { return x * 2; }
        int __stdcall cb2(int x) { return x * 3; }
    """)
    ptr_call1 = ffi.addressof(lib, 'call1')
    ptr_call2 = ffi.addressof(lib, 'call2')
    if sys.platform == 'win32' and not sys.maxsize > 2**32:
        pytest.raises(TypeError, lib.call1, ffi.addressof(lib, 'cb2'))
        pytest.raises(TypeError, ptr_call1, ffi.addressof(lib, 'cb2'))
        pytest.raises(TypeError, lib.call2, ffi.addressof(lib, 'cb1'))
        pytest.raises(TypeError, ptr_call2, ffi.addressof(lib, 'cb1'))
    assert lib.call1(ffi.addressof(lib, 'cb1')) == 500*999*2
    assert ptr_call1(ffi.addressof(lib, 'cb1')) == 500*999*2
    assert lib.call2(ffi.addressof(lib, 'cb2')) == -500*999*3
    assert ptr_call2(ffi.addressof(lib, 'cb2')) == -500*999*3

def test_win32_calling_convention_3():
    ffi = FFI()
    ffi.cdef("""
        struct point { int x, y; };

        int (*const cb1)(struct point);
        int (__stdcall *const cb2)(struct point);

        struct point __stdcall call1(int(*cb)(struct point));
        struct point call2(int(__stdcall *cb)(struct point));
    """)
    lib = verify(ffi, 'test_win32_calling_convention_3', r"""
        #ifndef _MSC_VER
        #  define __cdecl
        #  define __stdcall
        #endif
        struct point { int x, y; };
        int           cb1(struct point pt) { return pt.x + 10 * pt.y; }
        int __stdcall cb2(struct point pt) { return pt.x + 100 * pt.y; }
        struct point __stdcall call1(int(__cdecl *cb)(struct point)) {
            int i;
            struct point result = { 0, 0 };
            //printf("here1\n");
            //printf("cb = %p, cb1 = %p\n", cb, (void *)cb1);
            for (i = 0; i < 1000; i++) {
                struct point p = { i, -i };
                int r = cb(p);
                result.x += r;
                result.y -= r;
            }
            return result;
        }
        struct point __cdecl call2(int(__stdcall *cb)(struct point)) {
            int i;
            struct point result = { 0, 0 };
            for (i = 0; i < 1000; i++) {
                struct point p = { -i, i };
                int r = cb(p);
                result.x += r;
                result.y -= r;
            }
            return result;
        }
    """)
    ptr_call1 = ffi.addressof(lib, 'call1')
    ptr_call2 = ffi.addressof(lib, 'call2')
    if sys.platform == 'win32' and not sys.maxsize > 2**32:
        pytest.raises(TypeError, lib.call1, ffi.addressof(lib, 'cb2'))
        pytest.raises(TypeError, ptr_call1, ffi.addressof(lib, 'cb2'))
        pytest.raises(TypeError, lib.call2, ffi.addressof(lib, 'cb1'))
        pytest.raises(TypeError, ptr_call2, ffi.addressof(lib, 'cb1'))
    pt = lib.call1(ffi.addressof(lib, 'cb1'))
    assert (pt.x, pt.y) == (-9*500*999, 9*500*999)
    pt = ptr_call1(ffi.addressof(lib, 'cb1'))
    assert (pt.x, pt.y) == (-9*500*999, 9*500*999)
    pt = lib.call2(ffi.addressof(lib, 'cb2'))
    assert (pt.x, pt.y) == (99*500*999, -99*500*999)
    pt = ptr_call2(ffi.addressof(lib, 'cb2'))
    assert (pt.x, pt.y) == (99*500*999, -99*500*999)

def test_extern_python_1():
    import warnings
    ffi = FFI()
    with warnings.catch_warnings(record=True) as log:
        ffi.cdef("""
        extern "Python" {
            int bar(int, int);
            void baz(int, int);
            int bok(void);
            void boz(void);
        }
        """)
    assert len(log) == 0, "got a warning: %r" % (log,)
    lib = verify(ffi, 'test_extern_python_1', """
        static void baz(int, int);   /* forward */
    """)
    assert ffi.typeof(lib.bar) == ffi.typeof("int(*)(int, int)")
    with FdWriteCapture() as f:
        res = lib.bar(4, 5)
    assert res == 0
    assert f.getvalue() == (
        b"extern \"Python\": function _CFFI_test_extern_python_1.bar() called, "
        b"but no code was attached "
        b"to it yet with @ffi.def_extern().  Returning 0.\n")

    @ffi.def_extern("bar")
    def my_bar(x, y):
        seen.append(("Bar", x, y))
        return x * y
    assert my_bar != lib.bar
    seen = []
    res = lib.bar(6, 7)
    assert seen == [("Bar", 6, 7)]
    assert res == 42

    def baz(x, y):
        seen.append(("Baz", x, y))
    baz1 = ffi.def_extern()(baz)
    assert baz1 is baz
    seen = []
    baz(long(40), long(4))
    res = lib.baz(long(50), long(8))
    assert res is None
    assert seen == [("Baz", 40, 4), ("Baz", 50, 8)]
    assert type(seen[0][1]) is type(seen[0][2]) is long
    assert type(seen[1][1]) is type(seen[1][2]) is int

    @ffi.def_extern(name="bok")
    def bokk():
        seen.append("Bok")
        return 42
    seen = []
    assert lib.bok() == 42
    assert seen == ["Bok"]

    @ffi.def_extern()
    def boz():
        seen.append("Boz")
    seen = []
    assert lib.boz() is None
    assert seen == ["Boz"]

def test_extern_python_bogus_name():
    ffi = FFI()
    ffi.cdef("extern int abc;")
    lib = verify(ffi, 'test_extern_python_bogus_name', "int abc;")
    def fn():
        pass
    pytest.raises(ffi.error, ffi.def_extern("unknown_name"), fn)
    pytest.raises(ffi.error, ffi.def_extern("abc"), fn)
    assert lib.abc == 0
    e = pytest.raises(ffi.error, ffi.def_extern("abc"), fn)
    assert str(e.value) == ("ffi.def_extern('abc'): no 'extern \"Python\"' "
                            "function with this name")
    e = pytest.raises(ffi.error, ffi.def_extern(), fn)
    assert str(e.value) == ("ffi.def_extern('fn'): no 'extern \"Python\"' "
                            "function with this name")
    #
    pytest.raises(TypeError, ffi.def_extern(42), fn)
    pytest.raises((TypeError, AttributeError), ffi.def_extern(), "foo")
    class X:
        pass
    x = X()
    x.__name__ = x
    pytest.raises(TypeError, ffi.def_extern(), x)

def test_extern_python_bogus_result_type():
    ffi = FFI()
    ffi.cdef("""extern "Python" void bar(int);""")
    lib = verify(ffi, 'test_extern_python_bogus_result_type', "")
    #
    @ffi.def_extern()
    def bar(n):
        return n * 10
    with StdErrCapture() as f:
        res = lib.bar(321)
    assert res is None
    msg = f.getvalue()
    assert "rom cffi callback %r" % (bar,) in msg
    assert "rying to convert the result back to C:\n" in msg
    assert msg.endswith(
        "TypeError: callback with the return type 'void' must return None\n")

def test_extern_python_redefine():
    ffi = FFI()
    ffi.cdef("""extern "Python" int bar(int);""")
    lib = verify(ffi, 'test_extern_python_redefine', "")
    #
    @ffi.def_extern()
    def bar(n):
        return n * 10
    assert lib.bar(42) == 420
    #
    @ffi.def_extern()
    def bar(n):
        return -n
    assert lib.bar(42) == -42

def test_extern_python_struct():
    ffi = FFI()
    ffi.cdef("""
        struct foo_s { int a, b, c; };
        extern "Python" int bar(int, struct foo_s, int);
        extern "Python" { struct foo_s baz(int, int);
                          struct foo_s bok(void); }
    """)
    lib = verify(ffi, 'test_extern_python_struct',
                 "struct foo_s { int a, b, c; };")
    #
    @ffi.def_extern()
    def bar(x, s, z):
        return x + s.a + s.b + s.c + z
    res = lib.bar(1000, [1001, 1002, 1004], 1008)
    assert res == 5015
    #
    @ffi.def_extern()
    def baz(x, y):
        return [x + y, x - y, x * y]
    res = lib.baz(1000, 42)
    assert res.a == 1042
    assert res.b == 958
    assert res.c == 42000
    #
    @ffi.def_extern()
    def bok():
        return [10, 20, 30]
    res = lib.bok()
    assert [res.a, res.b, res.c] == [10, 20, 30]

def test_extern_python_long_double():
    ffi = FFI()
    ffi.cdef("""
        extern "Python" int bar(int, long double, int);
        extern "Python" long double baz(int, int);
        extern "Python" long double bok(void);
    """)
    lib = verify(ffi, 'test_extern_python_long_double', "")
    #
    @ffi.def_extern()
    def bar(x, l, z):
        seen.append((x, l, z))
        return 6
    seen = []
    lib.bar(10, 3.5, 20)
    expected = ffi.cast("long double", 3.5)
    assert repr(seen) == repr([(10, expected, 20)])
    #
    @ffi.def_extern()
    def baz(x, z):
        assert x == 10 and z == 20
        return expected
    res = lib.baz(10, 20)
    assert repr(res) == repr(expected)
    #
    @ffi.def_extern()
    def bok():
        return expected
    res = lib.bok()
    assert repr(res) == repr(expected)

def test_extern_python_signature():
    ffi = FFI()
    lib = verify(ffi, 'test_extern_python_signature', "")
    pytest.raises(TypeError, ffi.def_extern(425), None)
    pytest.raises(TypeError, ffi.def_extern, 'a', 'b', 'c', 'd')

def test_extern_python_errors():
    ffi = FFI()
    ffi.cdef("""
        extern "Python" int bar(int);
    """)
    lib = verify(ffi, 'test_extern_python_errors', "")

    seen = []
    def oops(*args):
        seen.append(args)

    @ffi.def_extern(onerror=oops)
    def bar(x):
        return x + ""
    assert lib.bar(10) == 0

    @ffi.def_extern(name="bar", onerror=oops, error=-66)
    def bar2(x):
        return x + ""
    assert lib.bar(10) == -66

    assert len(seen) == 2
    exc, val, tb = seen[0]
    assert exc is TypeError
    assert isinstance(val, TypeError)
    assert tb.tb_frame.f_code.co_name == "bar"
    exc, val, tb = seen[1]
    assert exc is TypeError
    assert isinstance(val, TypeError)
    assert tb.tb_frame.f_code.co_name == "bar2"
    #
    # a case where 'onerror' is not callable
    pytest.raises(TypeError, ffi.def_extern(name='bar', onerror=42),
                   lambda x: x)

def test_extern_python_stdcall():
    ffi = FFI()
    ffi.cdef("""
        extern "Python" int __stdcall foo(int);
        extern "Python" int WINAPI bar(int);
        static int (__stdcall * mycb1)(int);
        static int indirect_call(int);
    """)
    lib = verify(ffi, 'test_extern_python_stdcall', """
        #ifndef _MSC_VER
        #  define __stdcall
        #endif
        static int (__stdcall * mycb1)(int);
        static int indirect_call(int x) {
            return mycb1(x);
        }
    """)
    #
    @ffi.def_extern()
    def foo(x):
        return x + 42
    @ffi.def_extern()
    def bar(x):
        return x + 43
    assert lib.foo(100) == 142
    assert lib.bar(100) == 143
    lib.mycb1 = lib.foo
    assert lib.mycb1(200) == 242
    assert lib.indirect_call(300) == 342

def test_extern_python_plus_c():
    ffi = FFI()
    ffi.cdef("""
        extern "Python+C" int foo(int);
        extern "C +\tPython" int bar(int);
        int call_me(int);
    """)
    lib = verify(ffi, 'test_extern_python_plus_c', """
        int foo(int);
        #ifdef __GNUC__
        __attribute__((visibility("hidden")))
        #endif
        int bar(int);

        static int call_me(int x) {
            return foo(x) - bar(x);
        }
    """)
    #
    @ffi.def_extern()
    def foo(x):
        return x * 42
    @ffi.def_extern()
    def bar(x):
        return x * 63
    assert lib.foo(100) == 4200
    assert lib.bar(100) == 6300
    assert lib.call_me(100) == -2100

def test_introspect_function():
    ffi = FFI()
    ffi.cdef("float f1(double);")
    lib = verify(ffi, 'test_introspect_function', """
        float f1(double x) { return (float)x; }
    """)
    assert dir(lib) == ['f1']
    FUNC = ffi.typeof(lib.f1)
    assert FUNC.kind == 'function'
    assert FUNC.args[0].cname == 'double'
    assert FUNC.result.cname == 'float'
    assert ffi.typeof(ffi.addressof(lib, 'f1')) is FUNC

def test_introspect_global_var():
    ffi = FFI()
    ffi.cdef("extern float g1;")
    lib = verify(ffi, 'test_introspect_global_var', """
        float g1;
    """)
    assert dir(lib) == ['g1']
    FLOATPTR = ffi.typeof(ffi.addressof(lib, 'g1'))
    assert FLOATPTR.kind == 'pointer'
    assert FLOATPTR.item.cname == 'float'

def test_introspect_global_var_array():
    ffi = FFI()
    ffi.cdef("extern float g1[100];")
    lib = verify(ffi, 'test_introspect_global_var_array', """
        float g1[100];
    """)
    assert dir(lib) == ['g1']
    FLOATARRAYPTR = ffi.typeof(ffi.addressof(lib, 'g1'))
    assert FLOATARRAYPTR.kind == 'pointer'
    assert FLOATARRAYPTR.item.kind == 'array'
    assert FLOATARRAYPTR.item.length == 100
    assert ffi.typeof(lib.g1) is FLOATARRAYPTR.item

def test_introspect_integer_const():
    ffi = FFI()
    ffi.cdef("#define FOO 42")
    lib = verify(ffi, 'test_introspect_integer_const', """
        #define FOO 42
    """)
    assert dir(lib) == ['FOO']
    assert lib.FOO == ffi.integer_const('FOO') == 42

def test_introspect_typedef():
    ffi = FFI()
    ffi.cdef("typedef int foo_t;")
    lib = verify(ffi, 'test_introspect_typedef', """
        typedef int foo_t;
    """)
    assert ffi.list_types() == (['foo_t'], [], [])
    assert ffi.typeof('foo_t').kind == 'primitive'
    assert ffi.typeof('foo_t').cname == 'int'

def test_introspect_typedef_multiple():
    ffi = FFI()
    ffi.cdef("typedef signed char a_t, c_t, g_t, b_t;")
    lib = verify(ffi, 'test_introspect_typedef_multiple', """
        typedef signed char a_t, c_t, g_t, b_t;
    """)
    assert ffi.list_types() == (['a_t', 'b_t', 'c_t', 'g_t'], [], [])

def test_introspect_struct():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a; };")
    lib = verify(ffi, 'test_introspect_struct', """
        struct foo_s { int a; };
    """)
    assert ffi.list_types() == ([], ['foo_s'], [])
    assert ffi.typeof('struct foo_s').kind == 'struct'
    assert ffi.typeof('struct foo_s').cname == 'struct foo_s'

def test_introspect_union():
    ffi = FFI()
    ffi.cdef("union foo_s { int a; };")
    lib = verify(ffi, 'test_introspect_union', """
        union foo_s { int a; };
    """)
    assert ffi.list_types() == ([], [], ['foo_s'])
    assert ffi.typeof('union foo_s').kind == 'union'
    assert ffi.typeof('union foo_s').cname == 'union foo_s'

def test_introspect_struct_and_typedef():
    ffi = FFI()
    ffi.cdef("typedef struct { int a; } foo_t;")
    lib = verify(ffi, 'test_introspect_struct_and_typedef', """
        typedef struct { int a; } foo_t;
    """)
    assert ffi.list_types() == (['foo_t'], [], [])
    assert ffi.typeof('foo_t').kind == 'struct'
    assert ffi.typeof('foo_t').cname == 'foo_t'

def test_introspect_included_type():
    SOURCE = """
        typedef signed char schar_t;
        struct sint_t { int x; };
    """
    ffi1 = FFI()
    ffi1.cdef(SOURCE)
    ffi2 = FFI()
    ffi2.include(ffi1)
    verify(ffi1, "test_introspect_included_type_parent", SOURCE)
    verify(ffi2, "test_introspect_included_type", SOURCE)
    assert ffi1.list_types() == ffi2.list_types() == (
            ['schar_t'], ['sint_t'], [])

def test_introspect_order():
    ffi = FFI()
    ffi.cdef("union CFFIaaa { int a; }; typedef struct CFFIccc { int a; } CFFIb;")
    ffi.cdef("union CFFIg   { int a; }; typedef struct CFFIcc  { int a; } CFFIbbb;")
    ffi.cdef("union CFFIaa  { int a; }; typedef struct CFFIa   { int a; } CFFIbb;")
    verify(ffi, "test_introspect_order", """
        union CFFIaaa { int a; }; typedef struct CFFIccc { int a; } CFFIb;
        union CFFIg   { int a; }; typedef struct CFFIcc  { int a; } CFFIbbb;
        union CFFIaa  { int a; }; typedef struct CFFIa   { int a; } CFFIbb;
    """)
    assert ffi.list_types() == (['CFFIb', 'CFFIbb', 'CFFIbbb'],
                                ['CFFIa', 'CFFIcc', 'CFFIccc'],
                                ['CFFIaa', 'CFFIaaa', 'CFFIg'])

def test_bool_in_cpp():
    # this works when compiled as C, but in cffi < 1.7 it fails as C++
    ffi = FFI()
    ffi.cdef("bool f(void);")
    lib = verify(ffi, "test_bool_in_cpp", "char f(void) { return 2; }")
    assert lib.f() is True

def test_bool_in_cpp_2():
    ffi = FFI()
    ffi.cdef('int add(int a, int b);')
    lib = verify(ffi, "test_bool_bug_cpp", '''
        typedef bool _Bool;  /* there is a Windows header with this line */
        int add(int a, int b)
        {
            return a + b;
        }''', source_extension='.cpp')
    c = lib.add(2, 3)
    assert c == 5

def test_struct_field_opaque():
    ffi = FFI()
    ffi.cdef("struct a { struct b b; };")
    e = pytest.raises(TypeError, verify,
                       ffi, "test_struct_field_opaque", "?")
    assert str(e.value) == ("struct a: field 'a.b' is of an opaque"
                            " type (not declared in cdef())")
    ffi = FFI()
    ffi.cdef("struct a { struct b b[2]; };")
    e = pytest.raises(TypeError, verify,
                       ffi, "test_struct_field_opaque", "?")
    assert str(e.value) == ("struct a: field 'a.b' is of an opaque"
                            " type (not declared in cdef())")
    ffi = FFI()
    ffi.cdef("struct a { struct b b[]; };")
    e = pytest.raises(TypeError, verify,
                       ffi, "test_struct_field_opaque", "?")
    assert str(e.value) == ("struct a: field 'a.b' is of an opaque"
                            " type (not declared in cdef())")

def test_function_arg_opaque():
    pytest.skip("can currently declare a function with an opaque struct "
                 "as argument, but AFAICT it's impossible to call it later")

def test_function_returns_opaque():
    ffi = FFI()
    ffi.cdef("struct a foo(int);")
    e = pytest.raises(TypeError, verify,
                       ffi, "test_function_returns_opaque", "?")
    assert str(e.value) == ("function foo: 'struct a' is used as result type,"
                            " but is opaque")

def test_function_returns_union():
    ffi = FFI()
    ffi.cdef("union u1 { int a, b; }; union u1 f1(int);")
    lib = verify(ffi, "test_function_returns_union", """
        union u1 { int a, b; };
        static union u1 f1(int x) { union u1 u; u.b = x; return u; }
    """)
    assert lib.f1(51).a == 51

def test_function_returns_partial_struct():
    ffi = FFI()
    ffi.cdef("struct aaa { int a; ...; }; struct aaa f1(int);")
    lib = verify(ffi, "test_function_returns_partial_struct", """
        struct aaa { int b, a, c; };
        static struct aaa f1(int x) { struct aaa s = {0}; s.a = x; return s; }
    """)
    assert lib.f1(52).a == 52

def test_function_returns_float_complex():
    ffi = FFI()
    ffi.cdef("float _Complex f1(float a, float b);");
    if sys.platform == 'win32':
        lib = verify(ffi, "test_function_returns_float_complex", """
            #include <complex.h>
            static _Fcomplex f1(float a, float b) { return _FCbuild(a, 2.0f*b); }
        """)
    else:
        lib = verify(ffi, "test_function_returns_float_complex", """
            #include <complex.h>
            static float _Complex f1(float a, float b) { return a + I*2.0f*b; }
        """, no_cpp=True)    # <complex.h> fails on some systems with C++
    result = lib.f1(1.25, 5.1)
    assert type(result) == complex
    assert result.real == 1.25   # exact
    assert (result.imag != 2*5.1) and (abs(result.imag - 2*5.1) < 1e-5) # inexact

def test_function_returns_double_complex():
    ffi = FFI()
    ffi.cdef("double _Complex f1(double a, double b);");
    if sys.platform == 'win32':
        lib = verify(ffi, "test_function_returns_double_complex", """
            #include <complex.h>
            static _Dcomplex f1(double a, double b) { return _Cbuild(a, 2.0*b); }
        """)
    else:
        lib = verify(ffi, "test_function_returns_double_complex", """
            #include <complex.h>
            static double _Complex f1(double a, double b) { return a + I*2.0*b; }
        """, no_cpp=True)    # <complex.h> fails on some systems with C++
    result = lib.f1(1.25, 5.1)
    assert type(result) == complex
    assert result.real == 1.25   # exact
    assert result.imag == 2*5.1  # exact

def test_cdef_using_windows_complex():
    if sys.platform != 'win32':
        pytest.skip("only for MSVC")
    ffi = FFI()
    ffi.cdef("_Fcomplex f1(float a, float b); _Dcomplex f2(double a, double b);");
    lib = verify(ffi, "test_cdef_using_windows_complex", """
        #include <complex.h>
        static _Fcomplex f1(float a, float b) { return _FCbuild(a, 2.0f*b); }
        static _Dcomplex f2(double a, double b) { return _Cbuild(a, 2.0*b); }
    """)
    result = lib.f1(1.25, 5.1)
    assert type(result) == complex
    assert result.real == 1.25   # exact
    assert (result.imag != 2*5.1) and (abs(result.imag - 2*5.1) < 1e-5) # inexact
    result = lib.f2(1.25, 5.1)
    assert type(result) == complex
    assert result.real == 1.25   # exact
    assert result.imag == 2*5.1  # exact

def test_function_argument_float_complex():
    ffi = FFI()
    ffi.cdef("float f1(float _Complex x);");
    if sys.platform == 'win32':
        lib = verify(ffi, "test_function_argument_float_complex", """
            #include <complex.h>
            static float f1(_Fcomplex x) { return cabsf(x); }
        """)
    else:
        lib = verify(ffi, "test_function_argument_float_complex", """
            #include <complex.h>
            static float f1(float _Complex x) { return cabsf(x); }
        """, no_cpp=True)    # <complex.h> fails on some systems with C++
    x = complex(12.34, 56.78)
    result = lib.f1(x)
    assert abs(result - abs(x)) < 1e-5

def test_function_argument_double_complex():
    ffi = FFI()
    ffi.cdef("double f1(double _Complex);");
    if sys.platform == 'win32':
        lib = verify(ffi, "test_function_argument_double_complex", """
            #include <complex.h>
            static double f1(_Dcomplex x) { return cabs(x); }
        """)
    else:
        lib = verify(ffi, "test_function_argument_double_complex", """
            #include <complex.h>
            static double f1(double _Complex x) { return cabs(x); }
        """, no_cpp=True)    # <complex.h> fails on some systems with C++
    x = complex(12.34, 56.78)
    result = lib.f1(x)
    assert abs(result - abs(x)) < 1e-11

def test_typedef_array_dotdotdot():
    ffi = FFI()
    ffi.cdef("""
        typedef int foo_t[...], bar_t[...];
        extern int gv[...];
        typedef int mat_t[...][...];
        typedef int vmat_t[][...];
        """)
    lib = verify(ffi, "test_typedef_array_dotdotdot", """
        typedef int foo_t[50], bar_t[50];
        int gv[23];
        typedef int mat_t[6][7];
        typedef int vmat_t[][8];
    """)
    assert ffi.sizeof("foo_t") == 50 * ffi.sizeof("int")
    assert ffi.sizeof("bar_t") == 50 * ffi.sizeof("int")
    assert len(ffi.new("foo_t")) == 50
    assert len(ffi.new("bar_t")) == 50
    assert ffi.sizeof(lib.gv) == 23 * ffi.sizeof("int")
    assert ffi.sizeof("mat_t") == 6 * 7 * ffi.sizeof("int")
    assert len(ffi.new("mat_t")) == 6
    assert len(ffi.new("mat_t")[3]) == 7
    pytest.raises(ffi.error, ffi.sizeof, "vmat_t")
    p = ffi.new("vmat_t", 4)
    assert ffi.sizeof(p[3]) == 8 * ffi.sizeof("int")

def test_typedef_array_dotdotdot_usage():
    ffi = FFI()
    ffi.cdef("""
        typedef int foo_t[...];
        typedef int mat_t[...][...];
        struct s { foo_t a; foo_t *b; foo_t **c; };
        int myfunc(foo_t a, foo_t *b, foo_t **c);
        struct sm { mat_t a; mat_t *b; mat_t **c; };
        int myfuncm(mat_t a, mat_t *b, mat_t **c);
        """)
    lib = verify(ffi, "test_typedef_array_dotdotdot_usage", """
        typedef int foo_t[50];
        typedef int mat_t[6][7];
        struct s { foo_t a; foo_t *b; foo_t **c; };
        static int myfunc(foo_t a, foo_t *b, foo_t **c) { return (**c)[49]; }
        struct sm { mat_t a; mat_t *b; mat_t **c; };
        static int myfuncm(mat_t a, mat_t *b, mat_t **c) { return (**c)[5][6]; }
    """)
    assert ffi.sizeof("foo_t") == 50 * ffi.sizeof("int")
    p = ffi.new("struct s *")
    assert ffi.sizeof(p[0]) == 50 * ffi.sizeof("int") + 2 * ffi.sizeof("void *")
    p.a[49] = 321
    p.b = ffi.addressof(p, 'a')
    p.c = ffi.addressof(p, 'b')
    assert lib.myfunc(ffi.NULL, ffi.NULL, p.c) == 321
    #
    assert ffi.sizeof("mat_t") == 42 * ffi.sizeof("int")
    p = ffi.new("struct sm *")
    assert ffi.sizeof(p[0]) == 42 * ffi.sizeof("int") + 2 * ffi.sizeof("void *")
    p.a[5][6] = -321
    p.b = ffi.addressof(p, 'a')
    p.c = ffi.addressof(p, 'b')
    assert lib.myfuncm(ffi.NULL, ffi.NULL, p.c) == -321

def test_call_with_custom_field_pos():
    ffi = FFI()
    ffi.cdef("""
        struct foo { int x; ...; };
        struct foo f(void);
        struct foo g(int, ...);
    """)
    lib = verify(ffi, "test_call_with_custom_field_pos", """
        struct foo { int y, x; };
        struct foo f(void) {
            struct foo s = { 40, 200 };
            return s;
        }
        struct foo g(int a, ...) { return f(); }
    """)
    assert lib.f().x == 200
    e = pytest.raises(NotImplementedError, lib.g, 0)
    assert str(e.value) == (
        'ctype \'struct foo\' not supported as return value.  It is a '
        'struct declared with "...;", but the C calling convention may '
        'depend on the missing fields; or, it contains anonymous '
        'struct/unions.  Such structs are only supported '
        'as return value if the function is \'API mode\' and non-variadic '
        '(i.e. declared inside ffibuilder.cdef()+ffibuilder.set_source() '
        'and not taking a final \'...\' argument)')

def test_call_with_nested_anonymous_struct():
    if sys.platform == 'win32':
        pytest.skip("needs a GCC extension")
    ffi = FFI()
    ffi.cdef("""
        struct foo { int a; union { int b, c; }; };
        struct foo f(void);
        struct foo g(int, ...);
    """)
    lib = verify(ffi, "test_call_with_nested_anonymous_struct", """
        struct foo { int a; union { int b, c; }; };
        struct foo f(void) {
            struct foo s;
            s.a = 40;
            s.b = 200;
            return s;
        }
        struct foo g(int a, ...) { return f(); }
    """)
    assert lib.f().b == 200
    e = pytest.raises(NotImplementedError, lib.g, 0)
    assert str(e.value) == (
        'ctype \'struct foo\' not supported as return value.  It is a '
        'struct declared with "...;", but the C calling convention may '
        'depend on the missing fields; or, it contains anonymous '
        'struct/unions.  Such structs are only supported '
        'as return value if the function is \'API mode\' and non-variadic '
        '(i.e. declared inside ffibuilder.cdef()+ffibuilder.set_source() '
        'and not taking a final \'...\' argument)')

def test_call_with_bitfield():
    ffi = FFI()
    ffi.cdef("""
        struct foo { int x:5; };
        struct foo f(void);
        struct foo g(int, ...);
    """)
    lib = verify(ffi, "test_call_with_bitfield", """
        struct foo { int x:5; };
        struct foo f(void) {
            struct foo s = { 11 };
            return s;
        }
        struct foo g(int a, ...) { return f(); }
    """)
    assert lib.f().x == 11
    e = pytest.raises(NotImplementedError, lib.g, 0)
    assert str(e.value) == (
        "ctype 'struct foo' not supported as return value.  It is a struct "
        "with bit fields, which libffi does not support.  Such structs are "
        "only supported as return value if the function is 'API mode' and "
        "non-variadic (i.e. declared inside ffibuilder.cdef()+ffibuilder."
        "set_source() and not taking a final '...' argument)")

def test_call_with_zero_length_field():
    if sys.platform == 'win32':
        pytest.skip("zero-length field not supported by MSVC")
    ffi = FFI()
    ffi.cdef("""
        struct foo { int a; int x[0]; };
        struct foo f(void);
        struct foo g(int, ...);
    """)
    lib = verify(ffi, "test_call_with_zero_length_field", """
        struct foo { int a; int x[0]; };
        struct foo f(void) {
            struct foo s = { 42 };
            return s;
        }
        struct foo g(int a, ...) { return f(); }
    """)
    assert lib.f().a == 42
    e = pytest.raises(NotImplementedError, lib.g, 0)
    assert str(e.value) == (
        "ctype 'struct foo' not supported as return value.  It is a "
        "struct with a zero-length array, which libffi does not support."
        "  Such structs are only supported as return value if the function is "
        "'API mode' and non-variadic (i.e. declared inside ffibuilder.cdef()"
        "+ffibuilder.set_source() and not taking a final '...' argument)")

def test_call_with_union():
    ffi = FFI()
    ffi.cdef("""
        union foo { int a; char b; };
        union foo f(void);
        union foo g(int, ...);
    """)
    lib = verify(ffi, "test_call_with_union", """
        union foo { int a; char b; };
        union foo f(void) {
            union foo s = { 42 };
            return s;
        }
        union foo g(int a, ...) { return f(); }
    """)
    assert lib.f().a == 42
    e = pytest.raises(NotImplementedError, lib.g, 0)
    assert str(e.value) == (
        "ctype 'union foo' not supported as return value by libffi.  "
        "Unions are only supported as return value if the function is "
        "'API mode' and non-variadic (i.e. declared inside ffibuilder.cdef()"
        "+ffibuilder.set_source() and not taking a final '...' argument)")

def test_call_with_packed_struct():
    if sys.platform == 'win32':
        pytest.skip("needs a GCC extension")
    ffi = FFI()
    ffi.cdef("""
        struct foo { char y; int x; };
        struct foo f(void);
        struct foo g(int, ...);
    """, packed=True)
    lib = verify(ffi, "test_call_with_packed_struct", """
        struct foo { char y; int x; } __attribute__((packed));
        struct foo f(void) {
            struct foo s = { 40, 200 };
            return s;
        }
        struct foo g(int a, ...) {
            struct foo s = { 41, 201 };
            return s;
        }
    """)
    assert ord(lib.f().y) == 40
    assert lib.f().x == 200
    e = pytest.raises(NotImplementedError, lib.g, 0)
    assert str(e.value) == (
        "ctype 'struct foo' not supported as return value.  It is a "
        "'packed' structure, with a different layout than expected by libffi."
        "  Such structs are only supported as return value if the function is "
        "'API mode' and non-variadic (i.e. declared inside ffibuilder.cdef()"
        "+ffibuilder.set_source() and not taking a final '...' argument)")

def test_pack_not_supported():
    ffi = FFI()
    ffi.cdef("""struct foo { char y; int x; };""", pack=2)
    pytest.raises(NotImplementedError, verify,
                   ffi, "test_pack_not_supported", "")

def test_gcc_visibility_hidden():
    if sys.platform == 'win32':
        pytest.skip("test for gcc/clang")
    ffi = FFI()
    ffi.cdef("""
    int f(int);
    """)
    lib = verify(ffi, "test_gcc_visibility_hidden", """
    int f(int a) { return a + 40; }
    """, extra_compile_args=['-fvisibility=hidden'])
    assert lib.f(2) == 42

def test_override_default_definition():
    ffi = FFI()
    ffi.cdef("typedef long int16_t, char16_t;")
    lib = verify(ffi, "test_override_default_definition", "")
    assert ffi.typeof("int16_t") is ffi.typeof("char16_t") is ffi.typeof("long")

def test_char16_char32_type(no_cpp=False):
    if no_cpp is False and sys.platform == "win32":
        pytest.skip("aaaaaaa why do modern MSVC compilers still define "
                     "a very old __cplusplus value")
    ffi = FFI()
    ffi.cdef("""
        char16_t foo_2bytes(char16_t);
        char32_t foo_4bytes(char32_t);
    """)
    lib = verify(ffi, "test_char16_char32_type" + no_cpp * "_nocpp", """
    #if !defined(__cplusplus) || (!defined(_LIBCPP_VERSION) && __cplusplus < 201103L)
    typedef uint_least16_t char16_t;
    typedef uint_least32_t char32_t;
    #endif

    char16_t foo_2bytes(char16_t a) { return (char16_t)(a + 42); }
    char32_t foo_4bytes(char32_t a) { return (char32_t)(a + 42); }
    """, no_cpp=no_cpp)
    assert lib.foo_2bytes(u+'\u1234') == u+'\u125e'
    assert lib.foo_4bytes(u+'\u1234') == u+'\u125e'
    assert lib.foo_4bytes(u+'\U00012345') == u+'\U0001236f'
    pytest.raises(TypeError, lib.foo_2bytes, u+'\U00012345')
    pytest.raises(TypeError, lib.foo_2bytes, 1234)
    pytest.raises(TypeError, lib.foo_4bytes, 1234)

def test_char16_char32_plain_c():
    test_char16_char32_type(no_cpp=True)

def test_loader_spec():
    ffi = FFI()
    lib = verify(ffi, "test_loader_spec", "")
    if sys.version_info < (3,):
        assert not hasattr(lib, '__loader__')
        assert not hasattr(lib, '__spec__')
    else:
        assert lib.__loader__ is None
        assert lib.__spec__ is None

def test_realize_struct_error():
    ffi = FFI()
    ffi.cdef("""typedef ... foo_t; struct foo_s { void (*x)(foo_t); };""")
    lib = verify(ffi, "test_realize_struct_error", """
        typedef int foo_t; struct foo_s { void (*x)(foo_t); };
    """)
    pytest.raises(TypeError, ffi.new, "struct foo_s *")

def test_from_buffer_struct():
    ffi = FFI()
    ffi.cdef("""struct foo_s { int a, b; };""")
    lib = verify(ffi, "test_from_buffer_struct_p", """
        struct foo_s { int a, b; };
    """)
    p = ffi.new("struct foo_s *", [-219239, 58974983])
    q = ffi.from_buffer("struct foo_s[]", ffi.buffer(p))
    assert ffi.typeof(q) == ffi.typeof("struct foo_s[]")
    assert len(q) == 1
    assert q[0].a == p.a
    assert q[0].b == p.b
    assert q == p
    q = ffi.from_buffer("struct foo_s *", ffi.buffer(p))
    assert ffi.typeof(q) == ffi.typeof("struct foo_s *")
    assert q.a == p.a
    assert q.b == p.b
    assert q[0].a == p.a
    assert q[0].b == p.b
    assert q == p

def test_unnamed_bitfield_1():
    ffi = FFI()
    ffi.cdef("""struct A { char : 1; };""")
    lib = verify(ffi, "test_unnamed_bitfield_1", """
        struct A { char : 1; };
    """)
    p = ffi.new("struct A *")
    assert ffi.sizeof(p[0]) == 1
    # Note: on gcc, the type name is ignored for anonymous bitfields
    # and that's why the result is 1.  On MSVC, the result is
    # sizeof("char") which is also 1.

def test_unnamed_bitfield_2():
    ffi = FFI()
    ffi.cdef("""struct A {
        short c : 1; short : 1; short d : 1; short : 1; };""")
    lib = verify(ffi, "test_unnamed_bitfield_2", """
        struct A {
            short c : 1; short : 1; short d : 1; short : 1;
        };
    """)
    p = ffi.new("struct A *")
    assert ffi.sizeof(p[0]) == ffi.sizeof("short")

def test_unnamed_bitfield_3():
    ffi = FFI()
    ffi.cdef("""struct A { struct { char : 1; char : 1; } b; };""")
    lib = verify(ffi, "test_unnamed_bitfield_3", """
        struct A { struct { char : 1; char : 1; } b; };
    """)
    p = ffi.new("struct A *")
    assert ffi.sizeof(p[0]) == 1
    # Note: on gcc, the type name is ignored for anonymous bitfields
    # and that's why the result is 1.  On MSVC, the result is
    # sizeof("char") which is also 1.

def test_unnamed_bitfield_4():
    ffi = FFI()
    ffi.cdef("""struct A { struct {
        unsigned c : 1; unsigned : 1; unsigned d : 1; unsigned : 1; } a;
        };
        struct B { struct A a; };""")
    lib = verify(ffi, "test_unnamed_bitfield_4", """
        struct A { struct {
            unsigned c : 1; unsigned : 1; unsigned d : 1; unsigned : 1; } a;
        };
        struct B { struct A a; };
    """)
    b = ffi.new("struct B *")
    a = ffi.new("struct A *")
    assert ffi.sizeof(a[0]) == ffi.sizeof("unsigned")
    assert ffi.sizeof(b[0]) == ffi.sizeof(a[0])

def test_struct_with_func_with_struct_pointer_arg():
    ffi = FFI()
    ffi.cdef("""struct BinaryTree {
            int (* CompareKey)(struct BinaryTree *tree);
        };""")
    lib = verify(ffi, "test_struct_with_func_with_struct_pointer_arg", """
        struct BinaryTree {
            int (* CompareKey)(struct BinaryTree *tree);
        };
    """)
    ffi.new("struct BinaryTree *")

def test_struct_with_func_with_struct_arg():
    ffi = FFI()
    ffi.cdef("""struct BinaryTree {
            int (* CompareKey)(struct BinaryTree tree);
        };""")
    lib = verify(ffi, "test_struct_with_func_with_struct_arg", """
        struct BinaryTree {
            int (* CompareKey)(struct BinaryTree tree);
        };
    """)
    pytest.raises(RuntimeError, ffi.new, "struct BinaryTree *")

def test_passing_large_list():
    ffi = FFI()
    ffi.cdef("""void passing_large_list(long[]);""")
    lib = verify(ffi, "test_passing_large_list", """
        static void passing_large_list(long a[]) { }
    """)
    arg = list(range(20000000))
    lib.passing_large_list(arg)
    # assert did not segfault

def test_convert_api_mode_builtin_function_to_cdata():
    ffi = FFI()
    ffi.cdef(
        """struct s { int x; };
        struct s add1(struct s); struct s add2(struct s);
        int mycall(struct s(*)(struct s)); int mycall2(void *);""")
    lib = verify(ffi, "test_convert_api_mode_builtin_function_to_cdata", """
        struct s { int x; };
        static struct s add1(struct s a) {
            struct s r; r.x = a.x + 1; return r;
        }
        static struct s add2(struct s a) {
            struct s r; r.x = a.x + 2; return r;
        }
        static int mycall(struct s(*cb)(struct s)) {
            struct s a; a.x = 100;
            return cb(a).x;
        }
        static int mycall2(void *cb) {
            struct s a; a.x = 200;
            return ((struct s(*)(struct s))cb)(a).x;
        }
    """)
    s_ptr = ffi.new("struct s *", [42])
    s = s_ptr[0]
    assert lib.add1(s).x == 43
    assert lib.add2(s).x == 44
    assert lib.mycall(lib.add1) == 101
    assert lib.mycall(lib.add2) == 102
    assert lib.mycall2(lib.add1) == 201
    assert lib.mycall2(lib.add2) == 202
    s.x = -42
    my_array = ffi.new("struct s(*[2])(struct s)")
    my_array[0] = lib.add1
    my_array[1] = lib.add2
    assert my_array[0](s).x == -41
    assert my_array[1](s).x == -40
    s.x = 84
    p = ffi.cast("void *", lib.add1)
    assert ffi.cast("struct s(*)(struct s)", p)(s).x == 85
    q = ffi.cast("intptr_t", lib.add2)
    assert ffi.cast("struct s(*)(struct s)", q)(s).x == 86
    s.x = 300
    my_array_2 = ffi.new("void *[]", [lib.add1, lib.add2])
    assert ffi.cast("struct s(*)(struct s)", my_array_2[1])(s).x == 302
    assert ffi.typeof(lib.add1) == ffi.typeof("struct s(*)(struct s)")
