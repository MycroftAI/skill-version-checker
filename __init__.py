# Copyright 2017 Mycroft AI, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import re
import requests
from datetime import timedelta

from adapt.intent import IntentBuilder
from mycroft import Message
from mycroft.audio import wait_while_speaking, is_speaking
from mycroft.skills.core import MycroftSkill, intent_handler
from mycroft.version import (
    CORE_VERSION_MAJOR, CORE_VERSION_MINOR, CORE_VERSION_BUILD,
    CORE_VERSION_STR)
from mycroft.util.time import now_utc
from mycroft.configuration.config import LocalConf, USER_CONFIG


JESSIE_VERSION = '8'  # Stretch is '9'


def os_version():
    """ Find os version ID. """
    with open('/etc/os-release') as f:
        for line in f:
            elements = line.split('=')
            if elements[0] == 'VERSION_ID':
                return elements[1].strip().strip('"')


class VersionCheckerSkill(MycroftSkill):
    RELEASE_URL = 'https://api.github.com/repos/mycroftai/mycroft-core/releases/latest'  # nopep8

    def __init__(self):
        super(VersionCheckerSkill, self).__init__("VersionCheckerSkill")

        # Latest versions is at least the current version
        self.latest_ver = [CORE_VERSION_MAJOR,
                           CORE_VERSION_MINOR,
                           CORE_VERSION_BUILD]

    def initialize(self):
        # Update allowed version to current version if lower or incorrect
        current_allowed = self.config_core.get("max_allowed_core_version", 0)
        core_version_float = CORE_VERSION_MAJOR + CORE_VERSION_MINOR / 10
        if (not isinstance(current_allowed, float) or
                current_allowed < core_version_float):
            self.save_upgrade_permission([CORE_VERSION_MAJOR,
                                          CORE_VERSION_MINOR])

        # Start repeating event once aday to inform of new major version
        daily = 60 * 60 * 24  # seconds in a day
        self.schedule_repeating_event(self.daily_version_check,
                                      now_utc(),     # run asap
                                      60 * 60 * 24,  # repeat daily
                                      daily, name='DailyVersionCheck')

    def reschedule_reminder(self):
        self.remove_event('recognizer_loop:audio_output_end')
        self.cancel_scheduled_event('QueueNotice')
        self.cancel_scheduled_event('DailyVersionCheck')
        self.schedule_repeating_event(self.daily_version_check,
                                      None,          # wait to run
                                      60 * 60 * 24,  # seconds in a day
                                      name='DailyVersionCheck')

    @staticmethod
    def find_version(version_str):
        return list(map(int, version_str.split('.')))

    @staticmethod
    def ver_data(version_list):
        return {'major': version_list[0],
                'minor': version_list[1],
                'build': version_list[2]}

    def query_for_latest_ver(self):
        try:
            request = requests.get(self.RELEASE_URL)
            ver_str = request.json()['tag_name'].replace('release/v', '')
            self.latest_ver = self.find_version(ver_str)
        except Exception:
            self.log.exception('Could not find latest version. ')

    def get_allowed_ver(self):
        v = self.config_core.get("max_allowed_core_version", None)
        if v:
            # Convert 18.2 into [18, 2, 999]
            v = float(v)  # in case someone entered it as a string
            return [int(v), int(str(round(v-int(v),2))[2:]), 999]
        else:
            # assume current major/minor version is legit
            return [CORE_VERSION_MAJOR, CORE_VERSION_MINOR, 999]

    def upgrade_possible(self):
        """ Check if upgrade can be performed automatically.

        Returns:
            bool: True if automatic upgrade is possible else False
        """
        platform = self.config_core['enclosure'].get('platform', 'unknown')
        if platform == 'mycroft_mark_1':
            return True
        elif platform == 'picroft' and os_version() == JESSIE_VERSION:
            return True
        else:
            return False

    @intent_handler(IntentBuilder("").require("Check").require("Version"))
    def check_version(self, message):
        # Report the version of mycroft-core software
        self.query_for_latest_ver()
        cur_ver = [CORE_VERSION_MAJOR, CORE_VERSION_MINOR, CORE_VERSION_BUILD]
        new_ver = self.latest_ver
        allowed_ver = self.get_allowed_ver()
        self.log.info("Current version: "+str(cur_ver))
        self.log.info("Latest version: "+str(new_ver))
        self.log.info("Allowed version: "+str(allowed_ver))

        # display the version on the device screen and speak it
        self.enclosure.deactivate_mouth_events()
        self.enclosure.mouth_text(CORE_VERSION_STR + "b")  # b for Beta
        self.speak_dialog('version', self.ver_data(cur_ver), wait=True)
        self.enclosure.activate_mouth_events()

        if cur_ver == new_ver:
            self.speak_dialog('version.latest')
        elif new_ver > allowed_ver:
            self.inform_user()
        elif cur_ver < new_ver and self.upgrade_possible():
            # Ask user if they want to update immediately
            resp = self.ask_yesno('ask.upgrade',
                                  data=self.ver_data(new_ver))
            if resp == 'yes':
                self.speak_dialog('upgrade.started')
                self.save_upgrade_permission(self.latest_ver)
                # TODO: On Github install, should we tell users how to update?
                plat = self.config_core.get('enclosure', {}).get('platform')
                self.bus.emit(Message('system.update',
                                      {'is_paired': True,
                                       'platform': plat}))
            else:
                self.speak_dialog('upgrade.cancelled')
        else:
            self.speak_dialog('update.available', data=self.ver_data(new_ver))
        self.reschedule_reminder()

    @intent_handler(IntentBuilder("").require("Check").
                    require("PlatformBuild"))
    def check_platform_build(self, message):
        if 'platform_build' in self.config_core['enclosure']:
            # Report the platform build (aka firmware version)
            build = self.config_core['enclosure']['platform_build']
            self.enclosure.deactivate_mouth_events()
            self.enclosure.mouth_text(build)

            self.speak_dialog('platform.build', data={'build': build}, wait=True)

            self.enclosure.activate_mouth_events()
        else:
            self.speak_dialog('platform.build.none')
        # If this is a mainstream Linux, include basic version info
        try:
            opsys = re.sub(r'\\[a-z]{1}', ' ', open("/etc/issue").readline())
            # just in case issue file contains cruft decorative or otherwise
            if re.search(r'\w{2,}', opsys):
                self.speak('On operating system: ' + opsys)
        except Exception:
            self.log.exception('/etc/issue read failed. ')

    ######################################################################
    # Logic to handle changes in major version, e.g. 18.02.x -> 18.08.x
    # System checks once a day for new versions and will prompt the user
    # at next opportunity whenever there is a new major version (which
    # requires permission before updating)

    def daily_version_check(self, message):
        self.query_for_latest_ver()

        allowed_ver = self.get_allowed_ver()
        if self.latest_ver > allowed_ver:
            # At next opportunity, alert user about pending update
            self.add_event('recognizer_loop:audio_output_end',
                           self.on_user_activity)

    def on_user_activity(self, message):
        # When the unit speaks, consider the user active.  Queue up a
        # notice of available update in 30 seconds.
        self.cancel_scheduled_event('QueueNotice')
        pause = now_utc() + timedelta(seconds=30)
        self.schedule_event(self._queue_notice, pause, name='QueueNotice')

        # Queued to notify now, don't bug again until at least the next day
        self.remove_event('recognizer_loop:audio_output_end')
        self.cancel_scheduled_event('DailyVersionCheck')
        self.schedule_repeating_event(self.daily_version_check,
                                      None,          # wait to run
                                      60 * 60 * 24,  # seconds in a day
                                      name='DailyVersionCheck')

    def inform_user(self):
        """ Let the user know an update is ready.

        If the device is capable of auto-update ask to start otherwise give
        relevant instructions.
        """
        platform = self.config_core['enclosure'].get('platform', 'unknown')
        if platform == 'mycroft_mark_1':
            self._ask_about_major_upgrade()
        elif platform == 'picroft' and os_version() == JESSIE_VERSION:
            self._ask_about_major_upgrade()
        elif platform == 'picroft':
            self.speak_dialog('inform.picroft',
                              data=self.ver_data(self.latest_ver))
        else:
            self.speak_dialog('inform.github',
                              data=self.ver_data(self.latest_ver))

    def _queue_notice(self, message):
        if is_speaking():
            # Re-queue notice
            self.on_user_activity(message)
        else:
            self.inform_user()

    def _ask_about_major_upgrade(self):
        # Get user permission for major upgrade
        resp = self.ask_yesno('major.upgrade',
                              data=self.ver_data(self.latest_ver))
        if resp == 'yes':
            # Save consent
            self.save_upgrade_permission(self.latest_ver)
            self.speak_dialog('upgrade.started')
            plat = self.config_core.get('enclosure', {}).get('platform')
            self.bus.emit(Message('system.update',
                                  {'is_paired': True,
                                  'platform': plat}))
        else:
            self.speak_dialog('major.upgrade.declined')

    def save_upgrade_permission(self, ver):
        # Build version as float, e.g. [18,8,999] as 18.8
        float_ver = ver[0] + ver[1]/10  # assumes minor is <= 9
        new_conf_values = {"max_allowed_core_version": float_ver}

        # Save under the user (e.g. ~/.mycroft/mycroft.conf)
        user_config = LocalConf(USER_CONFIG)
        user_config.merge(new_conf_values)
        user_config.store()

        # Notify all processes to update their loaded configs
        self.bus.emit(Message('configuration.updated'))


def create_skill():
    return VersionCheckerSkill()
