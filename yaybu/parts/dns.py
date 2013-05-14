# Copyright 2012 Isotoma Limited
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

import logging

from yaybu.core.util import memoized, StateSynchroniser
from yay import ast, errors
from libcloud.dns.types import Provider as DNSProvider
from libcloud.dns.providers import get_driver as get_dns_driver
from libcloud.common.types import LibcloudError

logger = logging.getLogger(__name__)


class Zone(ast.PythonClass):

    """
    This part manages a single DNS zone

    mydns:
        create "yaybu.parts.dns:Zone":
            driver:
                id: AWS
                key:
                secret:
            domain: example.com
            type: master
            ttl: 60
            records:
              - name: www
                type: A
                data: 192.168.1.1
    """

    keys = []

    @property
    @memoized
    def driver(self):
        config = self.params['driver'].as_dict()
        self.driver_name = config['id']
        del config['id']
        driver = getattr(DNSProvider, self.driver_name)
        driver_class = get_dns_driver(driver)
        return driver_class(**config)

    def apply(self):
        simulate = self.root.simulate

        changed = self.synchronise_zone(logger, simulate)
        changed = changed or self.synchronise_records(logger, simulate)

        return changed

    def synchronise_zone(self, logger, simulate):
        s = StateSynchroniser(logger, simulate)

        domain = self.params['domain'].as_string().rstrip(".") + "."

        s.add_master_record(
            domain,
            domain = domain,
            type = self.params['type'].as_string("master"),
            ttl = self.params['ttl'].as_int(0),
            extra = self.params['extra'].as_dict({}),
            )

        for zone in self.driver.list_zones():
            if zone.domain == domain:
                s.add_slave_record(
                    domain = domain,
                    type = zone.type,
                    ttl = zone.ttl,
                    extra = zone.extra,
                    )

        return s.synchronise(
            self.driver.create_zone,
            self.driver.update_zone,
            None,
            )

    def synchronise_records(self, logger, simulate, zone=None):
        s = StateSynchroniser(logger, simulate)

        # Load the state from the config file into the synchroniser
        for rec in self.records:
            # FIXME: Catch error and raise an error with line number information
            type_enum = self.driver._string_to_record_type(rec.type.as_string('A'))

            s.add_master_record(
                rid = rec['name'].as_string(),
                name = rec['name'].as_string(),
                type = type_enum,
                data = rec['data'].as_string(),
                extra = rec['extra'].as_dict(),
                )

        # Load the state from libcloud into the synchroniser
        if zone:
            for rec in zone.list_records():
                s.add_slave_record(
                    rid = rec.name,
                    name = rec.name,
                    type = rec.type,
                    data = rec.data,
                    extra = rec.extra,
                    )

        return s.synchronise(
            zone.create_record,
            zone.update_record,
            zone.delete_record,
            )