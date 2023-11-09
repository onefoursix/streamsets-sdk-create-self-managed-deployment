#!/usr/bin/env python

'''
This script creates and starts a self-managed deployment on StreamSets Platform

Prerequisites:
 - Python 3.6+

 - StreamSets Platform SDK for Python v56.01+
   See: https://docs.streamsets.com/platform-sdk/latest/learn/installation.html

 - StreamSets Platform API Credentials for a user with Organization Administrator role

 - An active StreamSets Self-Managed Environment

This script reads CRED_ID and CRED_TOKEN values from environment variables set in advance,
you can run commands like this:

export CRED_ID="..."
export CRED_TOKEN="..."

Before running the script, review and set all of the necessary properties in a file named 'deployment.properties'
and edit the file stage-libs.json file to add or remove the stage libs (short names) needed for the deployment.  The
file names are not critical as they will be passed as args when running the script

Usage: $ python create-deployment.py <deployment-properties-file> <stage-libs-file>

Usage Example: $ python create-deployment.py deployment.properties stage-libs.json

'''

import datetime, json, os, stat, subprocess, sys, time
from configparser import ConfigParser
from streamsets.sdk import ControlHub

# Check the right number of command line args
if len(sys.argv) != 3:
    print('\nError; wrong number of arguments')
    print('Usage: $ python create-deployment.py <deployment-properties-file> <stage-libs-file>')
    print('Usage example: $ python create-deployment.py deployment.properties stage-libs.json\n')
   # sys.exit(-1)

# Get the properties from the command line
deployment_properties_file = sys.argv[1]
stage_lib_json_file = sys.argv[2]

# Validate the deployment properties files exists
if not os.path.isfile(deployment_properties_file):
    print('\nError loading deployment properties file: \'' + deployment_properties_file + '\'\n' )
    sys.exit(-1)

# Validate the stage-libs-json file exists
if not os.path.isfile(stage_lib_json_file):
    print('\nError loading stage-libs-json file: \'' + stage_lib_json_file + '\'\n' )
    sys.exit(-1)

# Some useful constants for reading properties
allow_null = True
do_not_allow_null = False

# Method to read a deployment property
def get_property(key, allow_null_value):
    value = deployment_properties[key].strip()
    if value == '' and not allow_null_value:
        print('\nError: no value for deployment property \'' + key + '\'\n')
        sys.exit(-1)
    return value

# Get CRED_ID from the environment
cred_id = os.getenv('CRED_ID')
if cred_id is None:
    print('Error: \'cred_id\' not found in the environment')
    sys.exit(1)

# Get CRED_TOKEN from the environment
cred_token = os.getenv('CRED_TOKEN')
if cred_id is None:
    print('Error: \'cred_token\' not found in the environment')
    sys.exit(1)

# Load the deployment.properties file
print('\nLoading properties from \'{}\''.format(deployment_properties_file))
config = ConfigParser()
config.read(deployment_properties_file)
deployment_properties = config['deployment']

# Get the values in the deployment.properties file
sch_url = get_property('SCH_URL', do_not_allow_null)
environment_name = get_property('ENVIRONMENT_NAME', do_not_allow_null)
deployment_name = get_property('DEPLOYMENT_NAME', do_not_allow_null)
deployment_tags = get_property('DEPLOYMENT_TAGS', allow_null)
use_websocket_tunneling = get_property('USE_WEBSOCKET_TUNNELING', do_not_allow_null).lower() == 'true'
sdc_version = get_property('SDC_VERSION', do_not_allow_null)
engine_labels = get_property('ENGINE_LABELS', allow_null)
sdc_max_cpu_load = get_property('SDC_MAX_CPU_LOAD', do_not_allow_null)
sdc_max_memory_used = get_property('SDC_MAX_MEMORY_USED', do_not_allow_null)
sdc_max_pipelines_running = get_property('SDC_MAX_PIPELINES_RUNNING',do_not_allow_null)
sdc_java_min_heap_mb = get_property('SDC_JAVA_MIN_HEAP_MB', do_not_allow_null)
sdc_java_max_heap_mb = get_property('SDC_JAVA_MAX_HEAP_MB', do_not_allow_null)
sdc_java_opts = get_property('SDC_JAVA_OPTS', allow_null)

# Get Ports
http_port = int(get_property('HTTP_PORT', do_not_allow_null))
https_port = int(get_property('HTTPS_PORT', do_not_allow_null))

# If Direct REST APIs are used rather than WebSocket tunneling
if not use_websocket_tunneling:
    sdc_hostname = get_property('SDC_HOSTNAME', do_not_allow_null)
    sdc_keystore = get_property('SDC_KEYSTORE', do_not_allow_null)
else:
    sdc_hostname = ''
    sdc_keystore = 'streamsets.jks'  # The default SDC keystore

# Set the protocol
if use_websocket_tunneling:
    protocol = 'http'
else:
    protocol = 'https'

# Check valid ports
if protocol == 'https' and https_port <= 1024:
    print('Error:invalid https port value: \'{}\'', format(https_port))
    sys.exit(1)
elif protocol == 'http' and http_port != 0 and http_port <= 1024:
    print('Error:invalid http port value: \'{}\'', format(http_port))
    sys.exit(1)

# Connect to Control Hub
print('Connecting to Control Hub')
sch = ControlHub(credential_id=cred_id, token=cred_token)

# Get the environment
print('Getting the environment')
try:
    environment = sch.environments.get(environment_name=environment_name)
    print('Found environment \'{}\''.format(environment_name))
except:
    print('Error: Environment \'{}\' not found'.format(environment_name))
    sys.exit(-1)

# Create a deployment builder
deployment_builder = sch.get_deployment_builder(deployment_type='SELF')

# Create the deployment
print('Creating deployment \'{}\''.format(deployment_name))
deployment_tags_array = deployment_tags.split(',')
deployment = deployment_builder.build(deployment_name=deployment_name,
                                      environment=environment,
                                      engine_type='DC',
                                      engine_version=sdc_version,
                                      deployment_tags=deployment_tags_array)

# Add the deployment to Control Hub
sch.add_deployment(deployment)

# Get the list of stage libs from the file stage-libs.json
print('Loading stage-libs list from \'{}\''.format(stage_lib_json_file))
try:
    with open(stage_lib_json_file, 'r') as f:
        stage_libs = json.load(f)
except Exception as e:
    print('\nError reading file \'{}\'\n'.format(stage_lib_json_file))
    sys.exit(1)

# These stage libs always need to be included
if 'dataformats' not in stage_libs:
    stage_libs.append('dataformats')
if 'dev' not in stage_libs:
    stage_libs.append('dev')
if 'basic' not in stage_libs:
    stage_libs.append('basic')

# Add the stage libs
print('Adding stage libs')
deployment.engine_configuration.stage_libs = stage_libs

# Engine config
engine_config = deployment.engine_configuration
engine_config.engine_labels.extend(engine_labels.split(','))
engine_config.max_cpu_load = sdc_max_cpu_load
engine_config.max_memory_used = sdc_max_memory_used
engine_config.max_pipelines_running = sdc_max_pipelines_running

# Engine Java config
java_config = engine_config.java_configuration
java_config.java_memory_strategy = 'ABSOLUTE'
java_config.minimum_java_heap_size_in_mb=sdc_java_min_heap_mb
java_config.maximum_java_heap_size_in_mb=sdc_java_max_heap_mb
java_config.java_options = sdc_java_opts

# Advanced Engine config
advanced_engine_config = engine_config.advanced_configuration

# sdc.properties
print('Loading sdc.properties')
with open('etc/sdc.properties') as f:
    sdc_properties = f.read()

#  Comment out the sdc.base.http.url property if using WebSockets,
#  or set the property if using Direct REST APIs
if use_websocket_tunneling:
    # Comment out the property
    sdc_properties = sdc_properties.replace('${SDC_BASE_URL_KEY}', '#sdc.base.http.url')
else:
    # create the SDC URL
    sdc_url = 'https://{}:{}'.format(sdc_hostname, https_port)
    sdc_properties = sdc_properties.replace('${SDC_BASE_URL_KEY}', 'sdc.base.http.url')
    sdc_properties = sdc_properties.replace('${SDC_BASE_HTTP_URL}', sdc_url)

sdc_properties = sdc_properties.replace('${HTTP_PORT}', str(http_port))
sdc_properties = sdc_properties.replace('${HTTPS_PORT}', str(https_port))
if not use_websocket_tunneling:
    sdc_properties = sdc_properties.replace('${KEYSTORE}', sdc_keystore)

# Set the updated sdc.properties file in the engine config
advanced_engine_config.data_collector_configuration = sdc_properties

# credential-stores.properties
print('Loading credential-stores.properties')
with open('etc/credential-stores.properties') as f:
    credential_stores = f.read()
advanced_engine_config.credential_stores = credential_stores

# security_policy
print('Loading security.policy')
with open('etc/security.policy') as f:
    security_policy = f.read()
advanced_engine_config.security_policy = security_policy

# log4j2
print('Loading sdc-log4j2.properties')
with open('etc/sdc-log4j2.properties') as f:
    log4j2 = f.read()
advanced_engine_config.log4j2 = log4j2

# proxy.properties
print('Loading proxy.properties')
with open('etc/proxy.properties') as f:
    proxy_properties = f.read()
advanced_engine_config.proxy_properties = proxy_properties

# Update the deployment
sch.update_deployment(deployment)

# Start the deployment
print('Starting the Deployment')
sch.start_deployment(deployment)
time.sleep(5)
if deployment.state == 'ACTIVE':
    print('Deployment is Active')
else:
    time.sleep(10)
    if deployment.state != 'ACTIVE':
        print('Error starting deployment')
        print ('See the Control Hub UI for details)')
        sys.exit(1)

print('Done')