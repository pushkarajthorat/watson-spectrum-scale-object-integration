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

from ConfigParser import ConfigParser

from stompest.config import StompConfig
from stompest.protocol import StompSpec
from stompest.sync import Stomp
from swift.common.utils import get_logger, parse_options, Timestamp
from swiftonfile.swift.common.utils import read_metadata
from swiftonfile.swift.common.utils import write_metadata
from watson_developer_cloud import VisualRecognitionV3


# Class responsible to listen to the provided STOMP queue and process the file.
class WatsonService(object):
    def __init__(self, config):
        self.queue_config = config.get('DEFAULT', 'queue_config')
        self.queue_name = config.get('DEFAULT', 'queue_name')
        self.visual_recognition_api_key = config.get('DEFAULT', 'visual_recognition_api_key')
        self.logger = self.get_logger(config)
        self.client = Stomp(StompConfig(self.queue_config))

    def get_logger(self, config):
        conf = dict(config.items('WATSON-LOGGER'))
        conf['log_name'] = 'watson_service'
        logger = get_logger(conf, log_route='watson_service')
        return logger
    

    def listen(self):
        self.client.connect()
        self.client.subscribe(self.queue_name, {StompSpec.ACK_HEADER: StompSpec.ACK_CLIENT_INDIVIDUAL})
        while True:
            frame = self.client.receiveFrame()
            file_name = frame.body
            headers = frame.headers
            
            self.process(file_name, Timestamp(headers['X-Timestamp']))            
            self.client.ack(frame)
        self.client.disconnect()

    # Sends the file_name to Watson Image Recog service, reterieves tags and updates it.
    def process(self, file_name, requestTS):
        self.logger.debug('Processing file: %s' % file_name)                  
        mergedMetadata = read_metadata(file_name)
        fileTS = Timestamp(mergedMetadata['X-Timestamp'])
        
        self.logger.debug('File Timestamp: %s' % mergedMetadata['X-Timestamp'])
        self.logger.debug('Request Timestamp: %s' % requestTS.isoformat)
        
        if fileTS != requestTS:
            return True
            
        images_file = open(file_name, 'rb')
        visual_recognition = VisualRecognitionV3('2016-05-20', api_key=self.visual_recognition_api_key)
        result = visual_recognition.classify(images_file=images_file)
        
        watsonTags = {}
        watsonTags_sorted = {}
        
        classes = result['images'][0]["classifiers"][0]["classes"] 
        
        for item in classes:
            watsonTags[item.get("class")] = item.get("score") 


        for key, value in sorted(watsonTags.iteritems(), key=lambda (k, v): (v, k), reverse=True)[:3]:
            watsonTags_sorted[key] = str(round(value * 100, 2)) + '%' 
        
        mergedMetadata.update({"X-Object-Meta-WatsonTags" : watsonTags_sorted})
        write_metadata(file_name, mergedMetadata)
        
if __name__ == '__main__':
    config_file, _ = parse_options()
    config = ConfigParser()
    try:
        config.read(config_file)
    except:
        raise Exception('Failed to read configuration file: %s ' % config_file)

    service = WatsonService(config)
    service.listen()

    
    

    


