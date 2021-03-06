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

from __future__ import absolute_import
import subprocess

import gevent
import requests

from yaybu import base, error


class GitChangeSource(base.GraphExternalAction):

    """
    This part manages listens to an external git repository for new commits,
    and pushes metadata into the graph. This could be used to trigger actions
    from commits.

    new GitChangeSource as changesource:

        repository: https://github.com/yaybu/yaybu
        polling-interval: 30


    The following metadata is now available to the graph (FIXME: tbd)

    tags
        A more recent version first list of tags, allowing you to do this::

            resources:
              - Checkout:
                  name: /usr/local/src/app
                  repository: {{ changesource.repository }}
                  tag: {{ changesource.tags[-1] }}

    branches
        Provides the current revision of each branch and can be used like this::

            resources:
              - Checkout:
                  name: /usr/local/src/app
                  repository: {{ changesource.repository }}
                  branch: master
                  revision: {{ changesource.branches.master }}
    """

    def _get_remote_metadata(self):
        cmd = ["git", "ls-remote", str(self.params.repository)]
        p = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()

        branches = {}
        tags = []

        for line in stdout.split("\n"):
            if not line.strip():
                continue
            sha, ref = line.split()

            if ref.startswith("refs/heads/"):
                branches[ref[11:]] = sha
            elif ref.startswith("refs/tags/"):
                if ref.endswith("^{}"):
                    continue
                tags.append(ref[10:])

        return branches, tags

    def _run(self, change_mgr):
        while True:
            branches, tags = self._get_remote_metadata()

            with change_mgr.changeset() as cs:
                old_branches = self.members["branches"]
                if branches != old_branches:
                    # One or more branches have changed
                    # There is no cache to bust for new branches
                    # We don't bother busting the cache for removed branches
                    # So we only look for pushes to existing branches
                    bw = self.members_wrapped.get_key("branches")
                    for name, sha in branches.items():
                        if name in old_branches and old_branches[name] != sha:
                            cs.bust(bw._get_key, name)
                    self.members["branches"] = branches

                if tags != self.members["tags"]:
                    self.members["tags"] = tags
                    cs.bust(self.members_wrapped._get_key, "tags")

            gevent.sleep(self.params["polling-interval"].as_int(default=60))

    def listen(self, change_mgr):
        return gevent.spawn(self._run, change_mgr)

    def test(self):
        # FIXME: Test that git repository exists and that any credentials we
        # have for it work
        pass

    def apply(self):
        branches, tags = self._get_remote_metadata()
        self.members["branches"] = branches
        self.members["tags"] = tags


class GitHubChangeSource(base.GraphExternalAction):

    """
    This part pushes metadata into the graph as new commits and releases are
    pushed to github

    new GitHubChangeSource as changesource:
        repository: yaybu/yaybu
    """

    def test(self):
        # FIXME: Test that github repository exists
        pass

    def _run(self):
        repository = self.params.repository.as_string()

        etag = None
        poll_interval = 60
        while True:
            headers = {}

            # As per the GitHub API docs - if we have an etag then provide it
            # This maximizes the number of API calls we can make - 304 Not
            # Modified does not count towards the API limits.
            if etag:
                headers['If-None-Match'] = etag

            resp = requests.get("https://api.github.com/repos/%s/events" % repository, headers=headers)
            if resp.status_code == 200:
                etag = resp.headers.get("ETag")
                for event in resp.json():
                    if event['type'] == 'DeploymentEvent':
                        deployment = event['payload']
                        print deployment

                    elif event['type'] == 'PushEvent':
                        push = event['payload']
                        print push

            elif resp.status_code == 304:
                print "NOT MODIFIED"

            elif resp.status_code == 400:
                print "REPO GONE AWAY"

            # Respect the Poll interval requested by GitHub (it may change when
            # the API is under heavy use)
            poll_interval = int(resp.headers.get("X-Poll-Interval") or poll_interval)
            gevent.sleep(poll_interval)

    def listen(self, change_mgr):
        return gevent.spawn(self._run)

    def apply(self):
        repository = self.params.repository.as_string()

        resp = requests.get("https://api.github.com/repos/%s/branches" % repository)
        if resp.status_code != 200:
            raise error.ValueError("Unable to get a list of branches for '%s'" % repository)
        branches = dict((v['name'], v['commit']['sha']) for v in resp.json())

        resp = requests.get("https://api.github.com/repos/%s/tags" % repository)
        if resp.status_code != 200:
            raise error.ValueError("Unable to get a list of tags for '%s'" % repository)
        tags = [dict(name=v['name'], sha=v['commit']['sha']) for v in resp.json()]

        self.members['branches'] = branches
        self.members['tags'] = tags
