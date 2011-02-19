
import sys
import logging

logger = logging.getLogger("audit")

class Change:
    pass

class AttributeChange(Change):
    """ A change to one attribute of a file's metadata """

class MetaChangeRenderer(type):

    renderers = {}

    def __new__(meta, class_name, bases, new_attrs):
        cls = type.__new__(meta, class_name, bases, new_attrs)
        if cls.renderer_for is not None:
            MetaChangeRenderer.renderers[(cls.renderer_type, cls.renderer_for)] = cls
        return cls

class ChangeRenderer:

    __metaclass__ = MetaChangeRenderer

    renderer_for = None
    renderer_type = None

    def __init__(self, original):
        self.original = original

    def render(self, logger):
        pass

class HTMLRenderer(ChangeRenderer):
    renderer_type = "html"

class TextRenderer(ChangeRenderer):
    renderer_type = "text"

class ResourceChange(Change):

    def __init__(self, changelog, resource):
        self.changelog = changelog
        self.resource = resource
        self.messages = []
        self.html_messages = []

    def __enter__(self):
        self.changelog.current_resource = self

    def info(self, message):
        self.messages.append((0, message))

    def notice(self, message):
        self.messages.append((1, message))

    def html_info(self, message):
        self.html_messages.append((0, message))

    def html_notice(self, message):
        self.html_messages.append((1, message))

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exc_type = exc_type
        self.exc_val = exc_val
        self.exc_tb = exc_tb
        self.changelog.current_resource = None
        if self.messages:
            rl = len(str(self.resource))
            if rl < 80:
                minuses = (77 - rl)/2
            else:
                minuses = 4
            self.changelog.write("/%s %r %s" % ("-"*minuses,
                                                self.resource,
                                                "-"*minuses))
            for level, msg in self.messages:
                if level == 0:
                    self.changelog.write("| %s" % msg)
                elif level == 1:
                    self.changelog.write("|====> %s" % msg)
            self.changelog.write("\%s" % ("-" *79,))
            self.changelog.write()
        if self.html_messages:
            self.changelog.write("<h2>%s</h2>" % self.resource)
            self.changelog.write("<ol>")
            for level, msg in self.messages:
                if level == 0:
                    self.changelog.write("<li>%s</li>" % msg)
                elif level == 1:
                    self.changelog.write("<li><b>%s</b></li>" % msg)
            self.changelog.write("</ol>")


class ChangeLog:

    """ Orchestrate writing output to a changelog. """

    def __init__(self, context):
        self.current_resource = None
        self.ctx = context

    def write(self, line=""):
        if self.ctx.html is not None:
            self.ctx.html.write(line)
            sys.stdout.write("\n")
        else:
            sys.stdout.write(line)
            sys.stdout.write("\n")

    def resource(self, resource):
        return ResourceChange(self, resource)

    def change(self, change):
        renderer = MetaChangeRenderer.renderers[("text", change.__class__)]
        renderer(change).render(self)
        if self.ctx.html is not None:
            renderer = MetaChangeRenderer.renderers[("html", change.__class__)]
            renderer(change).render(self)

    def info(self, message, *args, **kwargs):
        formatted = message.format(*args, **kwargs)
        logger.info(formatted)
        if self.ctx.html is None:
            self.current_resource.info(formatted)

    def notice(self, message, *args, **kwargs):
        formatted = message.format(*args, **kwargs)
        logger.warning(formatted)
        if self.ctx.html is None:
            self.current_resource.notice(formatted)

    def html_info(self, message, *args, **kwargs):
        formatted = message.format(*args, **kwargs)
        if self.ctx.html is not None:
            self.current_resource.html_info(formatted)

    def html_notice(self, message, *args, **kwargs):
        formatted = message.format(*args, **kwargs)
        if self.ctx.html is not None:
            self.current_resource.html_notice(formatted)
