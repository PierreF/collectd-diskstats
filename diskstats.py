#  Copyright 2010 Gregory Szorc
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
# This plugin reads data from /proc/diskstats
#
# It will only work on Linux 2.6
#
# To configure the plugin, you must specify the devices to monitor.
# The plugin takes a param 'Disk' whose string value is the exact
# device name. This param can be defined multiple times.
#
# e.g.
#
#<Plugin python>
#    ModulePath "/path/to/modules"
#    Import "diskstats"
#
#    <Module diskstats>
#        Disk sda
#        Disk sda1
#    </Module>
#</Plugin>
#
# Values from /proc/diskstats are increasing counters, to make values usable a
# delta is computed between two measurements. Delta could be either computed
# by this plugin or by collectd. This plugin compute the delta
# per-interval (usually 10 seconds). On the other hand, collectd compute the
# delta per-second.
#
# Note: This change is backward incompatible. Per-second value and
# per-interval (per 10 seconds with default config) values can not be mixed.
# In addition, because metric are send either as gauge (delta per-interval)
# or as counter (delta per-second), the metrics will not have the same name.
#
# This is configurable using the param 'DeltaPerSecond', which could be either
# 'yes' or 'no' (default to no).
#
# e.g.
#
#<Plugin python>
#    ModulePath "/path/to/modules"
#    Import "diskstats"
#
#    <Module diskstats>
#        DeltaPerSecond yes
#        [...]
#    </Module>
#</Plugin>
#
# The fields in /proc/diskstats are documented in Documentation/iostats.txt in
# the Linux kernel source tree.

import collectd

field_map = {
    1: 'reads_completed',
    2: 'reads_merged',
    3: 'sectors_read',
    4: 'reading_milliseconds',
    5: 'writes_completed',
    6: 'writes_merged',
    7: 'sectors_written',
    8: 'writing_milliseconds',
    9: 'io_inprogress',
    10: 'io_milliseconds',
    11: 'io_milliseconds_weighted'
}

disks = []

delta_per_second = False

previous_values = {}

def diskstats_config(c):
    global delta_per_second

    if c.values[0] != 'diskstats':
        return

    for child in c.children:
        if child.key == 'Disk':
            for v in child.values:
                if v not in disks:
                    disks.append(v)
                    if v not in previous_values:
                        previous_values[v] = {}
        elif child.key == 'DeltaPerSecond':
            if len(child.values) > 0 and child.values[0] is True:
                delta_per_second = True

def diskstats_read(data=None):
    # if no disks to monitor, do nothing
    if not len(disks):
        return

    fh = open('/proc/diskstats', 'r')

    values = collectd.Values(type='gauge', plugin='diskstats')
    values_counter = collectd.Values(type='counter', plugin='diskstats')

    for line in fh:
        fields = line.split()

        if len(fields) != 14:
            collectd.warning('format of /proc/diskstats not recognized: %s' % line)
            continue

        device = fields[2]

        # are we monitoring this device?
        if device not in disks:
            continue

        for i in range(1, 12):
            # no mapping
            if i == 6:
                continue

            value = int(fields[i+2])

            # field 9 is not a counter
            if i == 9:
                values.dispatch(plugin_instance=device, type_instance=field_map[i], values=[value])
                continue

            # when delta is per-second, send mertric as counter and let collectd
            # do the delta. In other case, this plugin will do the delta.
            if delta_per_second:
                values_counter.dispatch(plugin_instance=device, type_instance=field_map[i], values=[value])
                continue

            # if this is the first value, simply record and move on to next field
            if i not in previous_values[device]:
                previous_values[device][i] = value
                continue

            # else we have a previous value
            previous_value = previous_values[device][i]

            delta = None

            # we have wrapped around
            if previous_value > value:
                delta = 4294967296 - previous_value + value
            else:
                delta = value - previous_value

            # record the new previous value
            previous_values[device][i] = value

            values.dispatch(plugin_instance=device, type_instance=field_map[i], values=[delta])

    fh.close()

collectd.register_read(diskstats_read)
collectd.register_config(diskstats_config)

