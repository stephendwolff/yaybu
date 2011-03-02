from yaybutest.utils import TestCase
import pwd
import grp
import os
import stat

class TestFile(TestCase):

    def test_create_file(self):
        self.check_apply("""
            resources:
              - File:
                  name: /etc/somefile
                  owner: root
                  group: root
            """)

        self.failUnlessExists("/etc/somefile")

    def test_attributes(self):
        self.check_apply("""
            resources:
              - File:
                  name: /etc/somefile2
                  owner: nobody
                  group: nogroup
                  mode: 0666
            """)
        self.failUnlessExists("/etc/somefile2")
        st = os.stat(self.enpathinate("/etc/somefile2"))
        self.failUnless(pwd.getpwuid(st.st_uid)[0] != 'nobody')
        self.failUnless(grp.getgrgid(st.st_gid)[0] != 'nogroup')
        mode = stat.S_IMODE(st.st_mode)
        self.assertEqual(mode, 0666)

    def test_create_file_template(self):
        self.check_apply("""
            resources:
                - File:
                    name: /etc/templated
                    template: package://yaybutest.providers.file/template1.j2
                    template_args:
                        foo: this is foo
                        bar: 42
                    owner: root
                    group: root
                    """)
        self.failUnlessExists("/etc/templated")

    def test_remove_file(self):
        self.check_apply("""
            resources:
              - File:
                  name: /etc/toremove
            """)
        self.check_apply("""
            resources:
              - File:
                  name: /etc/toremove
                  policy: remove
            """)
        self.failUnless(not os.path.exists(self.enpathinate("/etc/toremove")))


    def test_empty(self):
        open(self.enpathinate("/etc/foo"), "w").write("foo")
        self.check_apply("""
            resources:
                - File:
                    name: /etc/foo
            """)

    def test_empty_nochange(self):
        open(self.enpathinate("/etc/foo"), "w").write("")
        rv = self.apply("""
            resources:
                - File:
                    name: /etc/foo
            """)
        self.assertEqual(rv, 255)


