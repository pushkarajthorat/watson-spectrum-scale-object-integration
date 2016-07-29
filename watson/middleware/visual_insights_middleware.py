# Copyright IBM Corp. 2016 All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from ConfigParser import ConfigParser, NoSectionError, NoOptionError
import os

from stompest.config import StompConfig
from stompest.sync import Stomp
from swift.common.exceptions import DiskFileError
from swift.common.http import HTTP_CREATED, HTTP_NO_CONTENT
from swift.common.ring import Ring
from swift.common.storage_policy import POLICIES
from swift.common.swob import wsgify, HTTPBadRequest, HTTPConflict
from swift.common.utils import get_logger
from swift.container.backend import ContainerBroker, DATADIR
from swift.proxy.controllers.base import get_container_info
from swiftonfile.swift.common.utils import read_metadata
from swiftonfile.swift.common.utils import write_metadata


SWIFT_STORAGE_POLICY_CONF_FILE = 'spectrum-scale-object-policies.conf'
SWIFT_SOF_OBJECT_CONF_FILE = 'object-server-sof.conf'
SOF_FUNCTION = 'file-and-object-access'

WATSON_QUEUE_CONF_FILE = '/etc/swift/watson-integration.conf'

# Middleware - intercepts the request and adds to the queue
class VisualInsightsMiddleware(object):


    def __init__(self, app, conf):
        # app is the final application
        self.app = app
        self.logger = get_logger(conf, log_route='watsonintegration')
        self.swift_dir = conf.get('swift_dir', '/etc/swift')
        self.policy_conf_file = os.path.join(self.swift_dir,
                                             SWIFT_STORAGE_POLICY_CONF_FILE)
        self.sof_object_conf_file = os.path.join(self.swift_dir,
                                                 SWIFT_SOF_OBJECT_CONF_FILE)
        self.sof_policy_list = self._create_sof_policy_list()
        
        self._read_watson_config()
        self._get_sof_config_values()


    def _create_sof_policy_list(self):
        sof_policy_list = set()
        functions = ''
        policy_config = ConfigParser()
        if os.path.exists(self.policy_conf_file):
            policy_config.read(self.policy_conf_file)
            for each_section in policy_config.sections():
                try:
                    functions = policy_config.get(each_section, 'functions')
                except (NoSectionError, NoOptionError):
                    pass
                if SOF_FUNCTION in functions:
                    policy_index = int(each_section.split(':')[1])
                    sof_policy_list.add(policy_index)
        else:
            self.logger.info('Storage policy file %s does not exist'\
                % self.policy_conf_file)
            raise Exception('Storage policy file %s does not exist'\
                % self.policy_conf_file)

        return sof_policy_list


    def _read_watson_config(self):
        watson_config = ConfigParser()
        try:
            watson_config.read(WATSON_QUEUE_CONF_FILE)
        except:
            self.logger.info('Failed to read the configuration file %s'\
                % WATSON_QUEUE_CONF_FILE)
            raise Exception('Failed to read the configuration file %s'\
                % WATSON_QUEUE_CONF_FILE)

        self.watson_visual_insight_queue_name = watson_config.get('DEFAULT', 'queue_name')
        self.watson_visual_insight_queue_config = watson_config.get('DEFAULT', 'queue_config')
        self.queue_client = Stomp(StompConfig(self.watson_visual_insight_queue_config))        


    def _get_sof_config_values(self):
        obj_config = ConfigParser()
        if os.path.exists(self.sof_object_conf_file):
            obj_config.read(self.sof_object_conf_file)
            try:
                self.sof_base_path = obj_config.get('DEFAULT', 'devices')
            except (NoSectionError, NoOptionError):
                self.logger.error('Config value not found in %s'\
                    % self.sof_object_conf_file)
                raise Exception('Config value not found in %s'\
                    % self.sof_object_conf_file)
        else:
            self.logger.info('SOF Object config file %s does not exist'\
                % self.sof_object_conf_file)
            raise Exception('SOF Object config file %s does not exist'\
                % self.sof_object_conf_file)


    def _convert_policy_to_index(self, req):
        policy_name = req.headers.get('X-Storage-Policy')
        if not policy_name:
            return int(POLICIES.default)
        policy = POLICIES.get_by_name(policy_name)
        if not policy:
            raise HTTPBadRequest(request=req,
                                 content_type="text/plain",
                                 body=("Invalid %s '%s'"
                                       % ('X-Storage-Policy', policy_name)))
        if policy.is_deprecated:
            body = 'Storage Policy %r is deprecated' % (policy.name)
            raise HTTPBadRequest(request=req, body=body)
        return int(policy)


    def _is_sof_policy(self, policy_index):
        # return True if policy index in sof policy list
        return policy_index in self.sof_policy_list


    def _get_dir_path(self, account, container, policy_index):
        # get the object ring from policy index
        obj_ring = POLICIES.get_object_ring(policy_index, self.swift_dir)
        # get the virtual device from the object ring
        _, nodes = obj_ring.get_nodes(account,
                                      container)
        sof_virt_device = nodes[0]['device']  # since we have only one virtual device
        return os.path.join(self.sof_base_path,
                            sof_virt_device,
                            account, container)

    @wsgify
    def __call__(self, req):
        original_resp = req.get_response(self.app)
        is_visualIns_present = 'X-Visual_Insights_Enable' in req.headers
        
        if is_visualIns_present and req.method.upper() == 'PUT':
            policy_index = self._convert_policy_to_index(req)
            if self._is_sof_policy(policy_index):
                _, account, container, obj = req.split_path(2, 4, True)
            
            ext = obj.split('.')
            ext = ext[len(ext) - 1]
            
            if ext in ['jpg', 'jpeg', 'png'] and account and container and obj:
                dir_path = self._get_dir_path(account, container, policy_index)
                object_path = dir_path + "/" + obj

                ts = '0'
                if 'X-Timestamp' in req.headers:
                    ts = req.headers['X-Timestamp']
                 
                self.queue_client.connect()
                self.logger.info('Sending %s  into queue' % object_path)
                self.queue_client.send(self.watson_visual_insight_queue_name,
                                       body=object_path, headers={'X-Timestamp': ts})
                
                self.logger.info('Successfully sent %s  into queue' % object_path)
                self.queue_client.disconnect()
                     
        return original_resp

def filter_factory(global_conf, **local_conf):
    conf = global_conf.copy()
    conf.update(local_conf)

    def visual_insights_middleware(app):
        return VisualInsightsMiddleware(app, conf)
    return visual_insights_middleware

