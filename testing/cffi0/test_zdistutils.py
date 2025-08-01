import sys, os, math, shutil
import pytest
from cffi import FFI, FFIError
from cffi.verifier import Verifier, _locate_engine_class, _get_so_suffixes
from cffi.ffiplatform import maybe_relative_path
from testing.udir import udir
from testing.support import load_dynamic

pytestmark = [
    pytest.mark.thread_unsafe(reason="worker threads would share a compilation directory"),
]


class DistUtilsTest(object):
    def setup_class(self):
        self.lib_m = "m"
        if sys.platform == 'win32':
            #there is a small chance this fails on Mingw via environ $CC
            import distutils.ccompiler
            if distutils.ccompiler.get_default_compiler() == 'msvc':
                self.lib_m = 'msvcrt'

    def teardown_class(self):
        if udir.isdir():
            udir.remove(ignore_errors=True)
        udir.ensure(dir=1)

    def test_locate_engine_class(self):
        cls = _locate_engine_class(FFI(), self.generic)
        if self.generic:
            # asked for the generic engine, which must not generate a
            # CPython extension module
            assert not cls._gen_python_module
        else:
            # asked for the CPython engine: check that we got it, unless
            # we are running on top of PyPy, where the generic engine is
            # always better
            if '__pypy__' not in sys.builtin_module_names:
                assert cls._gen_python_module

    def test_write_source(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there %s!*/\n#include <math.h>\n' % self
        v = Verifier(ffi, csrc, force_generic_engine=self.generic,
                     libraries=[self.lib_m])
        v.write_source()
        with open(v.sourcefilename, 'r') as f:
            data = f.read()
        assert csrc in data

    def test_write_source_explicit_filename(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there %s!*/\n#include <math.h>\n' % self
        v = Verifier(ffi, csrc, force_generic_engine=self.generic,
                     libraries=[self.lib_m])
        v.sourcefilename = filename = str(udir.join('write_source.c'))
        v.write_source()
        assert filename == v.sourcefilename
        with open(filename, 'r') as f:
            data = f.read()
        assert csrc in data

    def test_write_source_to_file_obj(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there %s!*/\n#include <math.h>\n' % self
        v = Verifier(ffi, csrc, force_generic_engine=self.generic,
                     libraries=[self.lib_m])
        try:
            from StringIO import StringIO
        except ImportError:
            from io import StringIO
        f = StringIO()
        v.write_source(file=f)
        assert csrc in f.getvalue()

    def test_compile_module(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there %s!*/\n#include <math.h>\n' % self
        v = Verifier(ffi, csrc, force_generic_engine=self.generic,
                     libraries=[self.lib_m])
        v.compile_module()
        assert v.get_module_name().startswith('_cffi_')
        if v.generates_python_module():
            mod = load_dynamic(v.get_module_name(), v.modulefilename)
            assert hasattr(mod, '_cffi_setup')

    def test_compile_module_explicit_filename(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there %s!2*/\n#include <math.h>\n' % self
        v = Verifier(ffi, csrc, force_generic_engine=self.generic,
                     libraries=[self.lib_m])
        basename = self.__class__.__name__[:10] + '_test_compile_module'
        v.modulefilename = filename = str(udir.join(basename + '.so'))
        v.compile_module()
        assert filename == v.modulefilename
        assert v.get_module_name() == basename
        if v.generates_python_module():
            mod = load_dynamic(v.get_module_name(), v.modulefilename)
            assert hasattr(mod, '_cffi_setup')

    def test_name_from_checksum_of_cdef(self):
        names = []
        for csrc in ['double', 'double', 'float']:
            ffi = FFI()
            ffi.cdef("%s sin(double x);" % csrc)
            v = Verifier(ffi, "#include <math.h>",
                         force_generic_engine=self.generic,
                         libraries=[self.lib_m])
            names.append(v.get_module_name())
        assert names[0] == names[1] != names[2]

    def test_name_from_checksum_of_csrc(self):
        names = []
        for csrc in ['123', '123', '1234']:
            ffi = FFI()
            ffi.cdef("double sin(double x);")
            v = Verifier(ffi, csrc, force_generic_engine=self.generic)
            names.append(v.get_module_name())
        assert names[0] == names[1] != names[2]

    def test_load_library(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there %s!3*/\n#include <math.h>\n' % self
        v = Verifier(ffi, csrc, force_generic_engine=self.generic,
                     libraries=[self.lib_m])
        library = v.load_library()
        assert library.sin(12.3) == math.sin(12.3)

    def test_verifier_args(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there %s!4*/#include "test_verifier_args.h"\n' % self
        udir.join('test_verifier_args.h').write('#include <math.h>\n')
        v = Verifier(ffi, csrc, include_dirs=[str(udir)],
                     force_generic_engine=self.generic,
                     libraries=[self.lib_m])
        library = v.load_library()
        assert library.sin(12.3) == math.sin(12.3)

    def test_verifier_object_from_ffi(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = "/*6%s*/\n#include <math.h>" % self
        lib = ffi.verify(csrc, force_generic_engine=self.generic,
                         libraries=[self.lib_m])
        assert lib.sin(12.3) == math.sin(12.3)
        assert isinstance(ffi.verifier, Verifier)
        with open(ffi.verifier.sourcefilename, 'r') as f:
            data = f.read()
        assert csrc in data

    def test_extension_object(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*7%s*/' % self + '''
    #include <math.h>
    #ifndef TEST_EXTENSION_OBJECT
    # error "define_macros missing"
    #endif
    '''
        lib = ffi.verify(csrc, define_macros=[('TEST_EXTENSION_OBJECT', '1')],
                         force_generic_engine=self.generic,
                         libraries=[self.lib_m])
        assert lib.sin(12.3) == math.sin(12.3)
        v = ffi.verifier
        ext = v.get_extension()
        assert 'distutils.extension.Extension' in str(ext.__class__) or \
               'setuptools.extension.Extension' in str(ext.__class__)
        assert ext.sources == [maybe_relative_path(v.sourcefilename)]
        assert ext.name == v.get_module_name()
        assert ext.define_macros == [('TEST_EXTENSION_OBJECT', '1')]

    def test_extension_forces_write_source(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there9!%s*/\n#include <math.h>\n' % self
        v = Verifier(ffi, csrc, force_generic_engine=self.generic,
                     libraries=[self.lib_m])
        assert not os.path.exists(v.sourcefilename)
        v.get_extension()
        assert os.path.exists(v.sourcefilename)

    def test_extension_object_extra_sources(self):
        ffi = FFI()
        ffi.cdef("double test1eoes(double x);")
        extra_source = str(udir.join('extension_extra_sources.c'))
        with open(extra_source, 'w') as f:
            f.write('double test1eoes(double x) { return x * 6.0; }\n')
        csrc = '/*9%s*/' % self + '''
        double test1eoes(double x);   /* or #include "extra_sources.h" */
        '''
        lib = ffi.verify(csrc, sources=[extra_source],
                         force_generic_engine=self.generic)
        assert lib.test1eoes(7.0) == 42.0
        v = ffi.verifier
        ext = v.get_extension()
        assert 'distutils.extension.Extension' in str(ext.__class__) or \
               'setuptools.extension.Extension' in str(ext.__class__)
        assert ext.sources == [maybe_relative_path(v.sourcefilename),
                               extra_source]
        assert ext.name == v.get_module_name()

    def test_install_and_reload_module(self, targetpackage='', ext_package=''):
        KEY = repr(self)
        if not hasattr(os, 'fork'):
            pytest.skip("test requires os.fork()")

        if targetpackage:
            udir.ensure(targetpackage, dir=1).ensure('__init__.py')
        sys.path.insert(0, str(udir))

        def make_ffi(**verifier_args):
            ffi = FFI()
            ffi.cdef("/* %s, %s, %s */" % (KEY, targetpackage, ext_package))
            ffi.cdef("double test1iarm(double x);")
            csrc = "double test1iarm(double x) { return x * 42.0; }"
            lib = ffi.verify(csrc, force_generic_engine=self.generic,
                             ext_package=ext_package,
                             **verifier_args)
            return ffi, lib

        childpid = os.fork()
        if childpid == 0:
            # in the child
            ffi, lib = make_ffi()
            assert lib.test1iarm(1.5) == 63.0
            # "install" the module by moving it into udir (/targetpackage)
            if targetpackage:
                target = udir.join(targetpackage)
            else:
                target = udir
            shutil.move(ffi.verifier.modulefilename, str(target))
            os._exit(0)
        # in the parent
        _, status = os.waitpid(childpid, 0)
        if not (os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0):
            raise AssertionError   # see error above in subprocess

        from cffi import ffiplatform
        prev_compile = ffiplatform.compile
        try:
            if targetpackage == ext_package:
                ffiplatform.compile = lambda *args: dont_call_me_any_more
            # won't find it in tmpdir, but should find it correctly
            # installed in udir
            ffi, lib = make_ffi()
            assert lib.test1iarm(0.5) == 21.0
        finally:
            ffiplatform.compile = prev_compile

    def test_install_and_reload_module_package(self):
        self.test_install_and_reload_module(targetpackage='foo_iarmp',
                                            ext_package='foo_iarmp')

    def test_install_and_reload_module_ext_package_not_found(self):
        self.test_install_and_reload_module(targetpackage='foo_epnf',
                                            ext_package='not_found')

    def test_tag(self):
        ffi = FFI()
        ffi.cdef("/* %s test_tag */ double test1tag(double x);" % self)
        csrc = "double test1tag(double x) { return x - 42.0; }"
        lib = ffi.verify(csrc, force_generic_engine=self.generic,
                         tag='xxtest_tagxx')
        assert lib.test1tag(143) == 101.0
        assert '_cffi_xxtest_tagxx_' in ffi.verifier.modulefilename

    def test_modulename(self):
        ffi = FFI()
        ffi.cdef("/* %s test_modulename */ double test1foo(double x);" % self)
        csrc = "double test1foo(double x) { return x - 63.0; }"
        modname = 'xxtest_modulenamexx%d' % (self.generic,)
        lib = ffi.verify(csrc, force_generic_engine=self.generic,
                         modulename=modname)
        assert lib.test1foo(143) == 80.0
        suffix = _get_so_suffixes()[0]
        fn1 = os.path.join(ffi.verifier.tmpdir, modname + '.c')
        fn2 = os.path.join(ffi.verifier.tmpdir, modname + suffix)
        assert ffi.verifier.sourcefilename == fn1
        assert ffi.verifier.modulefilename == fn2


class TestDistUtilsCPython(DistUtilsTest):
    generic = False

class TestDistUtilsGeneric(DistUtilsTest):
    generic = True
