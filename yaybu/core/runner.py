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

import optparse
import os
import sys
import logging
import logging.handlers
import collections
import traceback
import subprocess

import yay

from yaybu.core.shell import Shell
from yaybu.core import change
from yaybu.core import resource
from yaybu.core import error
from yaybu.core import remote
from yaybu.core import runcontext

logger = logging.getLogger("runner")

class LoaderError(Exception):
    pass



class Runner(object):

    resources = None

    def configure_logging(self, opts):
        """ configure the audit trail to log to file or to syslog """
        levels = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR,
            'critical': logging.CRITICAL,
            }

        log_level = levels.get(opts.log_level, None)
        if log_level is None:
            raise KeyError("Log level %s not recognised, terminating" % opts.log_level)
        if opts.logfile is not None:
            if opts.logfile == "-":
                logging.basicConfig(stream=sys.stdout,
                                    format="%(asctime)s %(levelname)s %(message)s",
                                    level=log_level)
            else:
                logging.basicConfig(filename=opts.logfile,
                                    filemode="a",
                                    format="%(asctime)s %(levelname)s %(message)s",
                                    level=log_level)
        else:
            facility = getattr(logging.handlers.SysLogHandler, "LOG_LOCAL%s" % opts.log_facility)
            handler = logging.handlers.SysLogHandler("/dev/log", facility=facility)
            formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            handler.setFormatter(formatter)
            logging.getLogger().addHandler(handler)
            simlog = logging.getLogger("simulation")
            simlog.setLevel(logging.DEBUG)
            simformatter = logging.Formatter("simulation: %(message)s")
            simhandler = logging.StreamHandler(sys.stdout)
            simhandler.setFormatter(simformatter)
            simlog.addHandler(simhandler)

    def run(self, opts, args):
        try:
            if opts.debug:
                opts.html = False
                opts.logfile = "-"
                opts.verbose = 2
            self.configure_logging(opts)

            if not opts.remote:
                ctx = runcontext.RunContext(args[0], opts)
            else:
                ctx = runcontext.RemoteRunContext(args[0], opts)

            config = ctx.get_config()

            self.resources = resource.ResourceBundle(config.get("resources", []))
            self.resources.bind()
            shell = Shell(context=ctx,
                          changelog=change.ChangeLog(ctx),
                          verbose=opts.verbose,
                          simulate=opts.simulate)
            if not self.resources.apply(shell, config):
                # nothing changed
                sys.exit(255)
            sys.exit(0)
        except error.ExecutionError, e:
            # this will have been reported by the context manager, so we wish to terminate
            # but not to raise it further. Other exceptions should be fully reported with
            # tracebacks etc automatically
            print >>sys.stderr, "Terminated due to execution error in processing"
            sys.exit(e.returncode)

def main():
    parser = optparse.OptionParser()
    parser.add_option("-s", "--simulate", default=False, action="store_true")
    parser.add_option("-p", "--ypath", default=[], action="append")
    parser.add_option("", "--log-facility", default="2", help="the syslog local facility number to which to write the audit trail")
    parser.add_option("", "--log-level", default="info", help="the minimum log level to write to the audit trail")
    parser.add_option("-d", "--debug", default=False, help="switch all logging to maximum, and write out to the console")
    parser.add_option("-l", "--logfile", default=None, help="The filename to write the audit log to, instead of syslog. Note: the standard console log will still be written to the console.")
    parser.add_option("-v", "--verbose", default=1, action="count", help="Write additional informational messages to the console log. repeat for even more verbosity.")
    parser.add_option("-H", "--html", default=None, help="Instead of writing progress information to the console, write an html progress log to this file.")
    parser.add_option("--host", default=None, action="store", help="A host to remotely run yaybu on")
    parser.add_option("--remote", default=False, action="store_true", help="Run yaybu.protocol client on stdio")

    opts, args = parser.parse_args()

    if len(args) != 1:
        parser.print_help()
        return 1

    if opts.host:
        r = remote.RemoteRunner()
    else:
        r = Runner()

    r.run(opts, args)

