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

""" Provides command-driven input to yaybu, using cmd.Cmd """

import os
import sys
import cmd
import optparse
import logging
import pprint

import yay
import yay.errors
from yaybu import error
from yaybu.core import util
from yaybu.core.queue import ChangeResponder
from yaybu.core.config import Config
from yaybu.util.ssh import get_ssh_transport_for_node

logger = logging.getLogger("yaybu.core.command")


class OptionParsingCmd(cmd.Cmd):

    def parser(self):
        p = optparse.OptionParser(usage="")
        p.remove_option("-h")
        return p

    def onecmd(self, line):
        """Interpret the argument as though it had been typed in response
        to the prompt.

        This may be overridden, but should not normally need to be;
        see the precmd() and postcmd() methods for useful execution hooks.
        The return value is a flag indicating whether interpretation of
        commands by the interpreter should stop.

        """
        cmd, arg, line = self.parseline(line)
        if not line:
            return self.emptyline()
        if cmd is None:
            return self.default(line)
        self.lastcmd = line
        if line == 'EOF':
            self.lastcmd = ''
        if cmd == '':
            return self.default(line)
        else:
            try:
                func = getattr(self, 'do_' + cmd)
            except AttributeError:
                return self.default(line)
            parser = self.parser()
            optparse_func = getattr(self, 'opts_' + cmd, lambda x: x)
            optparse_func(parser)
            opts, args = parser.parse_args(arg.split())

            try:
                return func(opts, args)
            except yay.errors.Error as e:
                if getattr(self, "debug", False):
                    import pdb
                    pdb.post_mortem()
                print e.get_string()
                return getattr(e, "returncode", 128)
            except KeyboardInterrupt:
                print "^C"

    def postcmd(self, stop, line):
        """Hook method executed just after a command dispatch is finished."""
        return False

    def cmdloop(self):
        try:
            return cmd.Cmd.cmdloop(self)
        except KeyboardInterrupt:
            print "\n%sexit" % self.prompt

    def aligned_docstring(self, arg):
        """ Return a docstring for a function, aligned properly to the left """
        try:
            doc = getattr(self, 'do_' + arg).__doc__
            if doc:
                return "\n".join([x.strip() for x in str(doc).splitlines()])
            else:
                return self.nohelp % (arg,)
        except AttributeError:
            return self.nohelp % (arg,)

    def do_help(self, opts, args):
        arg = " ".join(args)
        if arg:
            # XXX check arg syntax
            func = getattr(self, 'help_' + arg, None)
            if func is not None:
                func()
            else:
                print self.aligned_docstring(arg)
            parser = self.parser()
            optparse_func = getattr(self, 'opts_' + arg, lambda x: x)
            optparse_func(parser)
            parser.print_help()
        else:
            names = self.get_names()
            cmds_doc = []
            cmds_undoc = []
            help = {}
            for name in names:
                if name[:5] == 'help_':
                    help[name[5:]] = 1
            names.sort()
            # There can be duplicates if routines overridden
            prevname = ''
            for name in names:
                if name[:3] == 'do_':
                    if name == prevname:
                        continue
                    prevname = name
                    cmd = name[3:]
                    if cmd in help:
                        cmds_doc.append(cmd)
                        del help[cmd]
                    elif getattr(self, name).__doc__:
                        cmds_doc.append(cmd)
                    else:
                        cmds_undoc.append(cmd)
            self.stdout.write("%s\n" % str(self.doc_leader))
            self.print_topics(self.doc_header, cmds_doc, 15, 80)
            self.print_topics(self.misc_header, help.keys(), 15, 80)
            self.print_topics(self.undoc_header, cmds_undoc, 15, 80)

    def simple_help(self, command):
        self.do_help((), (command,))


class YaybuCmd(OptionParsingCmd):

    prompt = "yaybu> "
    interactive_shell = True
    Config = Config

    def __init__(
        self,
        config=None,
        ypath=(),
        verbose=2,
        logfile=None,
            debug=False):
        """ Global options are provided on the command line, before the
        command """
        cmd.Cmd.__init__(self)
        self.config = config
        self.ypath = ypath
        self.verbose = verbose
        self.logfile = logfile
        self.debug = debug

    @property
    def yaybufile(self):
        if self.config:
            return self.config

        directory = os.getcwd()
        while directory != "/":
            path = os.path.join(directory, "Yaybufile")
            if os.path.exists(path):
                return path
            directory = os.path.dirname(directory)

        # Ew. I might just refuse to support this.
        if os.path.exists("/Yaybufile"):
            return "/Yaybufile"

        raise error.MissingAsset(
            "Could not find Yaybufile in '%s' or any of its parents" % os.getcwd())

    def preloop(self):
        print util.version()
        print ""

    def _get_graph(self, opts, args):
        graph = self.Config()
        graph.simulate = getattr(opts, "simulate", True)
        graph.resume = getattr(opts, "resume", False)
        graph.no_resume = getattr(opts, "no_resume", False)
        if not len(self.ypath):
            self.ypath = [os.getcwd()]
        graph.ypath = self.ypath
        graph.verbose = self.verbose

        graph.name = "example"
        graph.load_uri(os.path.realpath(self.yaybufile))
        graph.set_arguments_from_argv(args)

        return graph

    def do_expand(self, opts, args):
        """
        usage: expand
        Prints the expanded YAML for the specified file.
        """
        graph = self._get_graph(opts, args)
        graph.readonly = True
        with graph.ui:
            resolved = graph.resolve()

        try:
            import yaml
            print yaml.safe_dump(resolved, default_flow_style=False)
        except ImportError:
            pprint.pprint(resolved)
        return 0

    def do_test(self, opts, args):
        """
        usage: test
        Test configuration is as valid as possible before deploying it
        """
        graph = self._get_graph(opts, args)
        graph.readonly = True
        with graph.ui:
            graph.resolve()
            for actor in graph.actors:
                actor.test()

        return 0

    def opts_up(self, parser):
        parser.add_option(
            "-s", "--simulate", default=False, action="store_true")
        parser.add_option("--resume", default=False, action="store_true",
                          help="Resume from saved events if terminated abnormally")
        parser.add_option("--no-resume", default=False, action="store_true",
                          help="Clobber saved event files if present and do not resume")

    def do_up(self, opts, args):
        """
        usage: up <name=value>...
        Create a new cluster, or update an existing cluster,
        in the cloud provider, using the configuration in Yaybufile
        if the configuration takes arguments these can be provided as
        name=value name=value...
        """
        graph = self._get_graph(opts, args)
        graph.readonly = True
        with graph.ui:
            graph.resolve()
            for actor in graph.actors:
                actor.test()

        graph = self._get_graph(opts, args)
        with graph.ui:
            graph.resolve()

        if not graph._changed:
            raise error.NothingChanged("No changes were required")

        return 0

    def opts_destroy(self, parser):
        parser.add_option(
            "-s", "--simulate", default=False, action="store_true")
        parser.add_option("--resume", default=False, action="store_true",
                          help="Resume from saved events if terminated abnormally")
        parser.add_option("--no-resume", default=False, action="store_true",
                          help="Clobber saved event files if present and do not resume")

    def do_destroy(self, opts, args):
        """
        usage: destroy
        """
        graph = self._get_graph(opts, args)
        graph.readonly = True
        with graph.ui:
            graph.resolve()
            for actor in graph.actors:
                actor.destroy()

        return 0

    def do_ssh(self, opts, args):
        """
        usage: ssh <name>
        SSH to the node specified.
        """
        if len(args) < 1:
            self.do_help((), ("ssh",))
            return

        graph = self._get_graph(opts, args[1:])
        graph.readonly = True

        node = graph.parse_expression(args[0])

        try:
            transport = get_ssh_transport_for_node(node)
        except yay.errors.NoMatching:
            transport = get_ssh_transport_for_node(node.server)

        from yaybu.ui.shell import PosixInteractiveShell
        PosixInteractiveShell.from_transport(transport).run()

    def do_status(self, opts, args):
        """
        usage: status
        Provide information on the cluster
        """
        graph = self._get_graph(opts, args)
        graph.readonly = True
        raise NotImplementedError(
            "I don't know how to find nodes in the graph yet")

    def opts_run(self, parser):
        parser.add_option(
            "-s", "--simulate", default=False, action="store_true")
        parser.add_option("--resume", default=False, action="store_true",
                          help="Resume from saved events if terminated abnormally")
        parser.add_option("--no-resume", default=False, action="store_true",
                          help="Clobber saved event files if present and do not resume")

    def do_run(self, opts, args):
        """
        usage: run
        Automatically update resources declared in Yaybufile as external events occur
        """
        graph = self._get_graph(opts, args)
        with graph.ui:
            graph.resolve()

            change_mgr = ChangeResponder(graph)
            greenlets = [change_mgr.listen()]
            for actor in graph.actors:
                if hasattr(actor, "listen"):
                    greenlets.append(actor.listen(change_mgr))
            import gevent
            gevent.joinall(greenlets)

    def opts_shell(self, parser):
        parser.add_option("-c", "--command", default=None, action="store")
        parser.add_option(
            "-i", "--interactive", default=False, action="store_true")

    def do_shell(self, opts, args):
        """
        usage: shell

        Parse a Yaybufile and drop into a python shell session for debugging
        """

        if "--" in args:
            graph_args = args[:args.index("--")]
            # script_args = args[args.index("--") + 1:]
        else:
            graph_args = args
            # script_args = []

        graph = self._get_graph(opts, graph_args)
        mylocals = {'graph': graph, '__name__': '__main__'}

        handled = False
        if opts.command:
            exec(opts.command, mylocals)
            handled = True
        elif args and args[0] == "-":
            execfile("/dev/stdin", mylocals)
            handled = True
        elif args:
            execfile(args[0], mylocals)
            handled = True

        if not handled or opts.interactive:
            import code
            try:
                import readline
                import rlcompleter
                readline.set_completer(
                    rlcompleter.Completer(mylocals).complete)
                readline.parse_and_bind("tab:complete")
            except ImportError:
                pass

            code.interact(local=mylocals)

    def do_selftest(self, opts, args):
        import unittest
        import mock
        from yaybu.util.backports import import_module
        import yaybu.tests
        import yay.tests

        loader = unittest.TestLoader()
        suite = unittest.TestSuite()

        for m in yaybu.tests.__all__:
            suite.addTests(loader.loadTestsFromModule(import_module("yaybu.tests.%s" % m)))

        for m in yay.tests.__all__:
            suite.addTests(loader.loadTestsFromModule(import_module("yay.tests.%s" % m)))

        stdout_isatty = sys.stdout.isatty()
        stdout_fileno = sys.stdout.fileno()

        runner = unittest.TextTestRunner(stream=sys.stderr)
        with mock.patch('sys.stdout'):
            sys.stdout.isatty.return_value = stdout_isatty
            sys.stdout.fileno.return_value = stdout_fileno
            sys.stdout.encoding = None
            with mock.patch('sys.stderr'):
                result = runner.run(suite)

        if not result.wasSuccessful():
            raise error.ExecutionError("Self-test failed, it is highly likely your yaybu installation is broken.")

    def do_exit(self, opts=None, args=None):
        """ Exit yaybu """
        raise SystemExit

    def do_EOF(self, opts, args):
        """ Exit yaybu """
        print
        self.do_exit()
