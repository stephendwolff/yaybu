# Copyright 2011 Isotoma Limited
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

import sys
import os
import stat
import logging

from yaybu import error
from yaybu.provisioner import resources
from yaybu.provisioner import provider
from yaybu.provisioner.changes import ShellCommand


class Link(provider.Provider):

    policies = (resources.link.LinkAppliedPolicy,)

    @classmethod
    def isvalid(self, *args, **kwargs):
        # TODO: validation could provide warnings based on things
        # that are not the correct state at the point of invocation
        # but that will be modified by the yaybu script
        return super(Link, self).isvalid(*args, **kwargs)

    def _get_owner(self, context):
        """ Return the uid for the resource owner, or None if no owner is
        specified. """
        if self.resource.owner is not None:
            try:
                return context.transport.getpwnam(self.resource.owner).pw_uid
            except KeyError:
                raise error.InvalidUser()

    def _get_group(self, context):
        """ Return the gid for the resource group, or None if no group is
        specified. """
        if self.resource.group is not None:
            try:
                return context.transport.getgrnam(self.resource.group).gr_gid
            except KeyError:
                raise error.InvalidGroup()

    def _stat(self, context):
        """ Extract stat information for the resource. """
        st = context.transport.lstat(self.resource.name)
        uid = st.st_uid
        gid = st.st_gid
        mode = stat.S_IMODE(st.st_mode)
        return uid, gid, mode

    def apply(self, context):
        changed = False
        name = self.resource.name
        to = self.resource.to
        exists = False
        uid = None
        gid = None
        mode = None
        isalink = False

        if not context.transport.exists(to):
            if not context.simulate:
                raise error.DanglingSymlink("Destination of symlink %r does not exist" % to)
            context.changelog.info("Destination of sylink %r does not exist" % to)

        owner = self._get_owner(context)
        group = self._get_group(context)

        try:
            linkto = context.transport.readlink(name)
            isalink = True
        except OSError:
            isalink = False

        if not isalink or linkto != to:
            if context.transport.lexists(name):
                context.change(ShellCommand(["/bin/rm", "-rf", name]))

            context.change(ShellCommand(["/bin/ln", "-s", self.resource.to, name]))
            changed = True

        try:
            linkto = context.transport.readlink(name)
            isalink = True
        except OSError:
            isalink = False

        if not isalink and not context.simulate:
            raise error.OperationFailed("Did not create expected symbolic link")

        if isalink:
            uid, gid, mode = self._stat(context)

        if owner is not None and owner != uid:
            context.change(ShellCommand(["/bin/chown", "-h", self.resource.owner, name]))
            changed = True

        if group is not None and group != gid:
            context.change(ShellCommand(["/bin/chgrp", "-h", self.resource.group, name]))
            changed = True

        return changed

class RemoveLink(provider.Provider):

    policies = (resources.link.LinkRemovedPolicy,)

    @classmethod
    def isvalid(self, *args, **kwargs):
        return super(RemoveLink, self).isvalid(*args, **kwargs)

    def apply(self, context):
        if context.transport.lexists(self.resource.name):
            if not context.transport.islink(self.resource.name):
                raise error.InvalidProvider("%r: %s exists and is not a link" % (self, self.resource.name))
            context.change(ShellCommand(["/bin/rm", self.resource.name]))
            return True
        return False
