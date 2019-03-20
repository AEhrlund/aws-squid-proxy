import os
import requests
import boto3
import paramiko

# AWS intance configuration
tag_name = 'aws-squid-proxy'
key_name = 'proxy-key'
security_group = 'proxy-security-group'
ssh_key = os.environ['OneDrive'] + '\\AWS\\proxy-key.pem'
ssh_user = 'ec2-user'
image_id = 'ami-86fe70f8'
instance_type = 't3.micro'

# Instance settings
shutdown_minutes = 60*3
docker_container_name = tag_name
port = 3128
squid_image = 'sameersbn/squid:3.5.27-1'

# Debug output
verbose = False

def debug_output(str):
    if (verbose):
        print(str)

def debug_command_output(stdout, stderr):
    debug_output('stdout: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')
    debug_output(stdout.read().decode('utf-8'))
    debug_output('stderr: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')
    debug_output(stderr.read().decode('utf-8'))
    debug_output('XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')

#

def find_instance():
    response = ec2.describe_instances()
    for instance in response['Reservations'][0]['Instances']:
        for tag in instance['Tags']:
            if tag['Key'] == 'Name' and tag['Value'] == tag_name:
                return instance['InstanceId']
    return None

def get_ssh_connection(instance_ip):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
    client.connect(instance_ip, username=ssh_user, key_filename=ssh_key)
    return client

def reget_ssh_connection(instance_ip, client):
    client.close()
    client.connect(instance_ip, username=ssh_user, key_filename=ssh_key)
    return client

def get_instance_ip(instance_id):
    response = ec2.describe_instances(InstanceIds=[instance_id])
    instance_ip = response['Reservations'][0]['Instances'][0]['PublicIpAddress']
    return instance_ip

def wait_until_started(instance_id):
    waiter = ec2.get_waiter('instance_status_ok')
    waiter.wait(InstanceIds=[instance_id])

def docker_stop(client):
    _, stdout, stderr = client.exec_command('sudo service docker stop')
    debug_command_output(stdout, stderr)

def docker_start(client):
    _, stdout, stderr = client.exec_command('sudo service docker start')
    debug_command_output(stdout, stderr)

def update_squid_conf(client, squid_conf):
    _, stdout, stderr = client.exec_command('echo -e "' + squid_conf + '" > squid.conf')
    debug_command_output(stdout, stderr)

def schedule_shutdown(client, minutes):
    client.exec_command('sudo shutdown -P +' + str(minutes) + ' &')

def get_squid_conf(ip):
    _squidconf = [
        'acl aclname src ' + ip + '/32',
        'acl SSL_ports port 443',
        'acl Safe_ports port 80',
        'acl Safe_ports port 443',
        'acl CONNECT method CONNECT',
        'http_access deny !Safe_ports',
        'http_access deny CONNECT !SSL_ports',
        'http_access allow all',
        'http_port 3128',
        'coredump_dir /var/spool/squid'
    ]
    squidconf = ''
    for line in _squidconf:
        squidconf += line + '\n'
    return squidconf

def get_myip():
    return requests.get('https://api.ipify.org/').text

def create_new_instance():
    response = ec2.run_instances(ImageId=image_id, InstanceType=instance_type, TagSpecifications=[{'ResourceType': 'instance','Tags': [{'Key': 'Name', 'Value': tag_name }]}], KeyName=key_name, SecurityGroups=[security_group], MinCount=1, MaxCount=1)
    return response['Instances'][0]['InstanceId']

def install_docker(client):
    _, stdout, stderr = client.exec_command('sudo yum install -y docker')
    debug_command_output(stdout, stderr)
    _, stdout, stderr = client.exec_command('sudo usermod -aG docker ' + ssh_user)
    debug_command_output(stdout, stderr)

def get_docker_squid(client):
    _, stdout, stderr = client.exec_command('docker pull ' + squid_image)
    debug_command_output(stdout, stderr)
    _, stdout, stderr = client.exec_command('docker run --name ' + docker_container_name + ' -d --restart=always --publish ' + str(port) + ':' + str(port) + ' --volume /home/ec2-user/squid.conf:/etc/squid/squid.conf ' + squid_image)

def update_instance(instance_id, squid_conf):
    response = ec2.describe_instances(InstanceIds=[instance_id])
    state = response['Reservations'][0]['Instances'][0]['State']
    debug_output('Current state: ' + str(state))
    if state['Code'] != 16: # if not running
        debug_output('Not started, restarting...')
        ec2.start_instances(InstanceIds=[instance_id])
        wait_until_started(instance_id)
        debug_output('...done')
    debug_output('Getting connection')
    instance_ip = get_instance_ip(instance_id)
    client = get_ssh_connection(instance_ip)
    debug_output('Stopping docker')
    docker_stop(client)
    debug_output('Updating squid.conf')
    update_squid_conf(client, squid_conf)
    debug_output('Starting docker')
    docker_start(client)
    debug_output('Schedule shutdown to ' + str(shutdown_minutes) + ' minutes')
    schedule_shutdown(client, shutdown_minutes)
    return instance_ip

def create_instance(squid_conf):
    debug_output('Creating AWS squid proxy instance...')
    instance_id = create_new_instance()
    debug_output('Created instance with id: ' + instance_id)
    debug_output('Waiting for instance to start...')
    wait_until_started(instance_id)
    debug_output('...done.')
    instance_ip = get_instance_ip(instance_id)
    debug_output('Instance public IP: ' + instance_ip)
    debug_output('Getting connection')
    client = get_ssh_connection(instance_ip)
    debug_output('Installing docker')
    install_docker(client)
    debug_output('Reconnecting to connection')
    client = reget_ssh_connection(instance_ip, client)
    debug_output('Updating squid.conf')
    update_squid_conf(client, squid_conf)
    debug_output('Starting docker')
    docker_start(client)
    debug_output('Get squid docker image')
    get_docker_squid(client)
    debug_output('Schedule shutdown to ' + str(shutdown_minutes) + ' minutes')
    schedule_shutdown(client, shutdown_minutes)
    return instance_ip

ec2 = boto3.client('ec2')
print('Searching for instance')
instance_id = find_instance()
squid_conf = get_squid_conf(get_myip())
if instance_id:
    print('Found instance: ' + instance_id)
    print('Updating...')
    instance_ip = update_instance(instance_id, squid_conf)
else:
    print('No instance found')
    print('Creating new instance...')
    instance_ip = create_instance(squid_conf)

print('Proxy started at: ' + instance_ip + ':' + str(port))
