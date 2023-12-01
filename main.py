import boto3
import paramiko
import time
import subprocess

# AWS credentials
aws_access_key = 'AKIAUKIUBKUGS2KWPS72'
aws_secret_key = 'TE/WJKj7YaWU7QQWUNmS6bTSoEOJ2LFE/aVxVPC7'
region = 'ap-south-1'  # e.g., 'us-west-1'
security_group_ids = ['sg-077647a78ad672d9a']

# Instance details
image_id = 'ami-0287a05f0ef0e9d9a'  # Amazon Machine Image ID
instance_type = 't2.micro'  # Instance type
key_name = 'my_key'  # Key pair name in AWS
name_tag = input("Enter Instance Name:")


# Create EC2 client
ec2 = boto3.client('ec2', aws_access_key_id=aws_access_key,
                   aws_secret_access_key=aws_secret_key, region_name=region)

try:
    # Describe the key pair
    response = ec2.describe_key_pairs(KeyNames=[key_name])

    if 'KeyPairs' in response and len(response['KeyPairs']) > 0:
        print(f"Key pair '{key_name}' exists in AWS")

except ec2.exceptions.ClientError as e:
    # Create a new key pair
    response = ec2.create_key_pair(KeyName=key_name)
    new_key_material = response['KeyMaterial']

    # Save the new key pair to a .pem file
    with open(f"{key_name}.pem", "w") as key_file:
        key_file.write(new_key_material)

    print(f"New key pair '{key_name}' created and saved to {key_name}.pem")

# Retrieve all instances with the specified name tag
instances = ec2.describe_instances(
    Filters=[
        {
            'Name': 'tag:Name',
            'Values': [name_tag]
        }
    ]
)

# Check if instances with the specified name tag exist
if len(instances['Reservations']) > 0:
    print(f"Instances with name tag '{name_tag}' exist.")
    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            print(f"Instance ID: {instance_id}")
    # Check the instance status
    response = ec2.describe_instance_status(InstanceIds=[instance_id])

    if len(response['InstanceStatuses']) > 0:
        instance_status = response['InstanceStatuses'][0]['InstanceState']['Name']
        print(f"Instance status: {instance_status}")

        # If the instance is stopped, start it
        if instance_status == 'stopped':
            ec2.start_instances(InstanceIds=[instance_id])
            print(f"Instance with ID {instance_id} has been started.")
        elif instance_status == 'running':
            print("Instance is already running.")
        else:
            print("Instance is in a different state and cannot be started automatically.")
    else:
        ec2.start_instances(InstanceIds=[instance_id])
        print(f"Instance with ID {instance_id} has been started.")

else:
    print(f"No instances found with name tag '{name_tag}'.")
    # Launch EC2 instance with a name tag
    response = ec2.run_instances(
        ImageId=image_id,
        InstanceType=instance_type,
        KeyName=key_name,
        SecurityGroupIds=security_group_ids,
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': name_tag
                    },
                ]
            },
        ]
    )

    instance_id = response['Instances'][0]['InstanceId']

# Wait for the instance to be running
waiter = ec2.get_waiter('instance_running')
waiter.wait(InstanceIds=[instance_id])

# Get instance details
instance = ec2.describe_instances(InstanceIds=[instance_id])
public_ip = instance['Reservations'][0]['Instances'][0]['PublicIpAddress']

print(f"Instance launched with ID: {instance_id}")
print(f"Public IP Address: {public_ip}")

# SSH Connection using Paramiko
key_path = f'/home/ec2-user/{key_name}.pem'  # Replace with the path to your .pem file
username = 'ubuntu'  # Replace with the username for your EC2 instance
remote_file_path = '/etc/resolv.conf' 

# Waiting for a few seconds to ensure the instance is fully initialized
time.sleep(30)

# Content to update in the remote file
text_to_append = "This text will be appended to the file on the remote instance."
command = f"echo '{text_to_append}' | sudo tee -a {remote_file_path}"

# Create a new SSH client
ssh_client = paramiko.SSHClient()
ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    # Load the private key (.pem file)
    private_key = paramiko.RSAKey.from_private_key_file(key_path)

    # Connect to the remote server
    ssh_client.connect(hostname=public_ip, username=username, pkey=private_key)

    print("Connected to the remote server!")

    # Execute the command on the remote instance
    stdin, stdout, stderr = ssh_client.exec_command(command)
    
    # Display the output (if any)
    for line in stdout:
        print(line.strip())


    # Close the SSH connection
    ssh_client.close()
    print("SSH connection closed.")
except Exception as e:
    print(f"Unable to connect or update file: {e}")
