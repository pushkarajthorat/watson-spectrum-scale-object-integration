#Integration of IBM Spectrum Scale Object with IBM Watson Cognitive services

This is demonstration of integration of IBM Spectrum Scale object with IBM Watson Cognitive services hosted at IBM Bluemix. This module utilizes Openstack Swift middlewares at proxy middleware chain and intercepts the request to check if the request satisfies the criteria for cognitive processing. If such request is selected then it is added to external [STOMP](http://stomp.github.io/)(Streaming Text Oriented Messaging Protocol based queue for further processing. 

In this module we use [IBM Watson's Visual Recognition service](https://www.ibm.com/smarterplanet/us/en/ibmwatson/developercloud/doc/visual-recognition/). Visual Recognition uses deep learning algorithms to analyze images for scenes, objects, faces, text, and other subjects that can give you insights into your visual content. The information received from this service is then stored in meatdata of that object.

**Note:** Here Objects/Images are sent over the wire through HTTPS protocol to this service to get the image information.

####LINCENCE
This module is licensed under Apache 2.0. Full license text is available in http://www.apache.org/licenses/LICENSE-2.0


####DEPLOYMENT
1. Prerequisites:
	- Get IBM Bluemix Visual Recognition API Key from https://console.ng.bluemix.net/catalog/services/visual-recognition
	- Stompest https://pypi.python.org/pypi/stompest/
	- Watson Developer Cloud SDK https://pypi.python.org/pypi/watson-developer-cloud
	- Apache Active MQ
	- Connectivity is needed for the server - gateway-a.watsonplatform.net
      Stompest library, Watson Developer Cloud SDK and Apache Active MQ is required to be installed on all the protocol nodes.

2. Copy and install rpm - dist/watsonintegration-0.1-1.noarch.rpm on all the protocol nodes.
3. Start Apache Active MQ, on all protocol nodes
4. Stop selinux


####CONFIGURATION AND USAGE
1. Update /etc/swift/watson-integration.conf, on all protocol nodes
	- 'visual_recognition_api_key' with the key generated from bluemix.net.
	- 'queue_config' appropriately depending on Apache Active MQ configuration.
2. Update /etc/swift/proxy-server.conf, on *any* protocol nodes
	- Update [pipeline:main] section, add - 'watson-integration' before 'proxy-server' (without quotes)
	- Add below section at end of the file:
	`
	[filter:watson-integration]
        paste.filter_factory=watson.middleware.visual_insights_middleware:filter_factory`
	- Issue 'mmccr  fput proxy-server.conf /etc/swift/proxy-server.conf'
3. Start watsonintegration service on all protcol nodes.
4. Create a SwiftOnFile policy and create a container with it.
5. Issue a request
`
      $ swift upload -H "X-Visual_Insights_Enable:true" <container_name> <object_name>
`
	Ensure request has - 'X-Visual_Insights_Enable:true' and object is a jpg/gif file to trigger the middleware.

6. Check Watson metadata tags: 
`
      $ swift stat <container_name> <object_name>
`

####COMPILATION
To compile RPM use:
`
      $ python setup.py bdist_rpm
`
      
####FILE LIST

	README.txt                                          README file.
	
	dist/watsonintegration-0.1-1.noarch.rpm             Installable RPM
	dist/watsonintegration-0.1-1.src.rpm                Installable RPM + Source
	dist/watsonintegration-0.1.tar.gz                   Source ONLY.
	
	MANIFEST.in                                         MANIFEST file, required by dist_utils ( setup.py )
	setup.py                                            build file.
	service/watsonintegration.service                   Service configuration file for starting / stopping watson service. This service is responsible for updating the objects on disk.
	watson/middleware/visual_insights_middleware.py     Proxy middleware; intercepts requests and adds in STOMP based queue (Apache Active MQ)
	watson/consumer/watson_service.py                   Watson service script.
	etc/watson-integration.conf                         Configuration file, used by both middleware and service file.
	
	LICENSE                                             LICENCE file.
	

####LOG FILES
On all protocol nodes:
	/var/log/swift/watson-service.error
	/var/log/swift/watson-service.log
	
Logging level can be increased by updating 'log_level' in: /etc/swift/watson-integration.conf
