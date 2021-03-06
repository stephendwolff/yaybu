# Copyright 2013 Isotoma Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os
import pkgutil
from yaybu.tests.provisioner_fixture import TestCase
from yaybu import error


def sibpath(filename):
    return os.path.join(os.path.dirname(__file__), filename)


class TestLink(TestCase):

    def symlink(self, a, b):
        self.transport.execute(["ln", "-s", a, b])

    def test_create_link(self):
        self.check_apply("""
            resources:
              - Link:
                  name: /etc/somelink
                  to: /etc
                  owner: root
                  group: root
            """)

        self.failUnlessExists("/etc/somelink")

    def test_remove_link(self):
        self.symlink("/", "/etc/toremovelink")
        self.check_apply("""
            resources:
              - Link:
                  name: /etc/toremovelink
                  policy: remove
            """)
        self.failIfExists("/etc/toremovelink")

    def test_already_exists(self):
        self.symlink("/", "/etc/existing")
        self.assertRaises(error.NothingChanged, self.apply, """
            resources:
              - Link:
                  name: /etc/existing
                  to: /
        """)
        self.failUnlessEqual(self.transport.readlink("/etc/existing"), "/")

    def test_already_exists_notalink(self):
        """ Test for the path already existing but is not a link. """
        self.transport.put("/bar_notalink", "")
        self.transport.put("/foo", "")

        self.check_apply("""
            resources:
                - Link:
                    name: /bar_notalink
                    to: /foo
            """)

        self.failUnlessEqual(self.transport.readlink("/bar_notalink"), "/foo")

    def test_already_exists_pointing_elsewhere(self):
        """ Test for the path already existing but being a link to somewhere else. """
        self.transport.put("/baz", "")
        self.transport.put("/foo", "")
        self.symlink("/baz", "/bar_elsewhere")
        self.check_apply("""
            resources:
                - Link:
                    name: /bar_elsewhere
                    to: /foo
            """)
        self.failUnlessEqual(self.transport.readlink("/bar_elsewhere"), "/foo")

    def test_dangling(self):
        self.assertRaises(error.DanglingSymlink, self.apply, """
        resources:
             - Link:
                 name: /etc/test_dangling
                 to: /etc/not_there
        """)

    def test_unicode(self):
        self.check_apply(pkgutil.get_data("yaybu.tests", "assets/link_unicode1.yay"))
