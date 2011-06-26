import os
import sys
from yaybutest.utils import TestCase
from yaybu.core import error

class TestEvents(TestCase):

    def test_nochange(self):
        self.check_apply("""
            resources:
              - Directory:
                  name: /etc/wibble
            """)

        rv = self.apply("""
            resources:
              - Directory:
                  name: /etc/wibble

              - File:
                  name: /frob/somedir/foo
                  policy:
                     apply:
                         when: apply
                         on: /etc/wibble
            """)
        self.assertEqual(rv, error.NothingChanged.returncode)

    def test_recover(self):
        rv = self.apply("""
            resources:
              - Directory:
                  name: /etc/somedir

              - Directory:
                  name: /frob/somedir

              - File:
                  name: /frob/somedir/foo
                  policy:
                     apply:
                         when: apply
                         on: Directory[/etc/somedir]
            """)
        self.assertEqual(rv, error.PathComponentMissing.returncode)

        self.check_apply("""
            resources:
              - Directory:
                  name: /etc/somedir

              - Directory:
                  name: /frob

              - Directory:
                  name: /frob/somedir

              - File:
                  name: /frob/somedir/foo
                  policy:
                     apply:
                         when: apply
                         on: Directory[/etc/somedir]

            """,
               "--resume")

        self.failUnlessExists("/frob/somedir/foo")

