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

import mycroft.util
from adapt.intent import IntentBuilder

from mycroft import Message
from mycroft.skills.core import MycroftSkill
from mycroft.version import (
    CORE_VERSION_MAJOR, CORE_VERSION_MINOR, CORE_VERSION_BUILD,
    CORE_VERSION_STR )


class VersionCheckerSkill(MycroftSkill):
    RELEASE_URL = 'https://api.github.com/repos/mycroftai/mycroft-core/releases/latest'

    def __init__(self):
        super(VersionCheckerSkill, self).__init__("VersionCheckerSkill")

    def initialize(self):
        intent = IntentBuilder('CheckVersion').require('Check') \
            .require('Version').build()
        self.register_intent(intent, self.check_version)

        intent = IntentBuilder('CheckPlatformBuild').require('Check') \
            .require('PlatformBuild')
        self.register_intent(intent, self.check_platform_build)

    @staticmethod
    def find_version(version_str):
        return list(map(int, version_str.split('.')))

    @staticmethod
    def ver_data(version_list):
        return {'major': version_list[0],
                'minor': version_list[1],
                'build': version_list[2]}

    def check_version(self, message):
        # Report the version of mycroft-core software

        # display the version on the device screen and speak it
        cur_ver = [CORE_VERSION_MAJOR, CORE_VERSION_MINOR, CORE_VERSION_BUILD]
        self.enclosure.deactivate_mouth_events()
        self.enclosure.mouth_text(CORE_VERSION_STR + "b")  # b for Beta
        self.speak_dialog('version', self.ver_data(cur_ver))
        mycroft.util.wait_while_speaking()
        self.enclosure.activate_mouth_events()

        try:
            # Obtain the most recent release's verion # from Github
            request = requests.get(self.RELEASE_URL)
            new_ver_str = request.json()['tag_name'].replace('release/v', '')
            new_ver = self.find_version(new_ver_str)
            new_ver = [18,8,0]  # TODO: Testing only!!!!!

            allowed_ver = self.config_core.get("max_allowed_core_version",
                                               cur_ver)

            self.log.info("Current version: "+str(cur_ver))
            self.log.info("Latest version: "+str(new_ver))
            self.log.info("Allowed version: "+str(allowed_ver))

            if cur_ver == new_ver:
                self.speak_dialog('version.latest')
            elif new_ver > allowed_ver:
                # Get user permission for major upgrade
                resp = self.ask_yesno('major.upgrade',
                                      data=self.ver_data(new_ver))
                if resp == 'yes':
                    # TODO write the local value str(new_ver[0])+"."+str(new_ver[1])
                    self.save_upgrade_permission(new_ver)
                    self.speak_dialog('upgrade.started')
                    self.emitter.emit(Message('system.update'))
                else:
                    self.speak_dialog('major.upgrade.declined')
            elif cur_ver < new_ver:
                # Ask user if they want to update immediately
                resp = self.ask_yesno('ask.upgrade',
                                      data={'new_version': new_ver_str})
                if resp == 'yes':
                    self.speak_dialog('upgrade.started')
                    self.emitter.emit(Message('system.update'))
                else:
                    self.speak_dialog('upgrade.cancelled')

        except Exception:
            self.log.exception('Could not find latest version. ')

        # NOTE: intentionally sticking with this deprecated API instead
        # of mycroft.audio.wait_while_speaking() so that this skill
        # works on 0.8.15+

    def save_upgrade_permission(self, ver):
        from mycroft.configuration.config import (
            LocalConf, USER_CONFIG, Configuration
        )

        float_ver = ver[0] + ver[1]/10
        new_conf_values = { "max_allowed_core_version": float_ver }

        user_config = LocalConf(USER_CONFIG)
        user_config.merge(new_conf_values)
        user_config.store()

        self.emitter.emit(Message('configuration.updated'))

    def check_platform_build(self, message):
        if 'platform_build' in self.config_core['enclosure']:
            # Report the platform build (aka firmware version)
            build = self.config_core['enclosure']['platform_build']
            self.enclosure.deactivate_mouth_events()
            self.enclosure.mouth_text(build)

            self.speak_dialog('platform.build', data={'build': build})

            mycroft.util.wait_while_speaking()
            self.enclosure.activate_mouth_events()
        else:
            self.speak_dialog('platform.build.none')
        # If this is a mainstream Linux, include basic version info
        try:
            opsys = re.sub(r'\\[a-z]{1}', ' ', open("/etc/issue").readline())
            # just in case issue file contains cruft decorative or otherwise
            if re.search('\w{2,}',opsys):
                self.speak('On operating system: ' + opsys)
        except Exception:
            self.log.exception('/etc/issue read failed. ')

    def stop(self):
        pass


def create_skill():
    return VersionCheckerSkill()
