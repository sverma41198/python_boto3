import boto3
import sys
import paramiko

region = sys.argv[1]

def create_vpc_igw_route_table_public_subnet(vpc_name, vpc_cidr_block, subnet_cidr_block):
    ec2 = boto3.client('ec2', region_name= region)  # Replace 'your_region' with your desired AWS region

    # Check if VPC with the given name exists
    response = ec2.describe_vpcs(
        Filters=[
            {'Name': 'tag:Name', 'Values': [vpc_name]}
        ]
    )

    existing_vpcs = response['Vpcs']

    if existing_vpcs:
        vpc_id = existing_vpcs[0]['VpcId']
        print(f"A VPC with name '{vpc_name}' already exists with ID: {vpc_id}")
            # Get Subnet ID by name and VPC ID
        subnet_response = ec2.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'tag:Name', 'Values': [f'msys-infra-{region}-subnet']}
            ]
        )

        subnets = subnet_response['Subnets']
        subnet_id = subnets[0]['SubnetId']
        return vpc_id,subnet_id

    else:
        # Create a new VPC if it doesn't exist
        vpc_response = ec2.create_vpc(
            CidrBlock=vpc_cidr_block,
            AmazonProvidedIpv6CidrBlock=False
        )
        vpc_id = vpc_response['Vpc']['VpcId']

        # Add Name tag to the new VPC
        ec2.create_tags(
            Resources=[vpc_id],
            Tags=[{'Key': 'Name', 'Value': vpc_name}]
        )
        print(f"Created a new VPC with name '{vpc_name}' and ID: {vpc_id}")

    # Create an internet gateway
    igw_name= f'msys-infra-{region}-igw'
    igw_response = ec2.create_internet_gateway()
    igw_id = igw_response['InternetGateway']['InternetGatewayId']
    ec2.create_tags(
        Resources=[igw_id],
        Tags=[{'Key': 'Name', 'Value': igw_name}]  # Replace 'MyIGW' with your desired name
    )

    # Attach internet gateway to VPC
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    print(f"Attached Internet Gateway {igw_id} to VPC {vpc_id}")

    # Create a route table and associate it with the VPC
    route_table_response = ec2.create_route_table(VpcId=vpc_id)
    route_table_id = route_table_response['RouteTable']['RouteTableId']

    # Create a route for internet access
    ec2.create_route(
        DestinationCidrBlock='0.0.0.0/0',
        GatewayId=igw_id,
        RouteTableId=route_table_id
    )
    print(f"Created route table {route_table_id} for Internet access in VPC {vpc_id}")

    # Create a public subnet
    subnet_response = ec2.create_subnet(
        VpcId=vpc_id,
        CidrBlock=subnet_cidr_block
    )
    subnet_id = subnet_response['Subnet']['SubnetId']

    # Associate subnet with the route table
    ec2.associate_route_table(RouteTableId=route_table_id, SubnetId=subnet_id)
    print(f"Created public subnet {subnet_id} associated with route table {route_table_id}")

    # Tag resources
    ec2.create_tags(
        Resources=[route_table_id],
        Tags=[{'Key': 'Name', 'Value': f'msys-infra-{region}-route-table'}]  # Replace with your desired tags
    )

        # Tag resources
    ec2.create_tags(
        Resources=[subnet_id],
        Tags=[{'Key': 'Name', 'Value': f'msys-infra-{region}-subnet'}]  # Replace with your desired tags
    )
    return vpc_id, subnet_id

def check_and_create_security_group(group_name, group_description, vpc_id):
    ec2 = boto3.client('ec2', region_name= region)  # Replace 'your_region' with your desired AWS region

    # Check if the security group with the given name exists
    response = ec2.describe_security_groups(
        Filters=[
            {'Name': 'group-name', 'Values': [group_name]},
            {'Name': 'vpc-id', 'Values': [vpc_id]}
        ]
    )

    existing_groups = response['SecurityGroups']

    if existing_groups:
        group_id = existing_groups[0]['GroupId']
        print(f"A security group with name '{group_name}' already exists with ID: {group_id}")
        return group_id
    else:
        # Create a new security group if it doesn't exist
        group_response = ec2.create_security_group(
            GroupName=group_name,
            Description=group_description,
            VpcId=vpc_id
        )
        new_group_id = group_response['GroupId']

            # Authorize SSH ingress rule
        ec2.authorize_security_group_ingress(
            GroupId= new_group_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]  # Allow SSH from anywhere
                }
            ]
        )

        print(f"Created a new security group with name '{group_name}' and ID: {new_group_id}")
        return new_group_id

def launch_ec2_instance(vpc_id, subnet_id, security_group_id):
    ec2 = boto3.client('ec2', region_name= region)  # Replace 'your_region' with your desired AWS region
    # Instance details
    image_id = 'ami-0e83be366243f524a'  # Amazon Machine Image ID
    instance_type = 't2.micro'  # Instance type
    key_name = f'msys-infra-{region}-private-key'  # Key pair name in AWS
    name_tag = f'msys-infra-{region}-vm'
    

    # response = ec2.describe_key_pairs(KeyNames=[key_name])

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
            NetworkInterfaces=[{
            'SubnetId': subnet_id,
            'DeviceIndex': 0,
            'AssociatePublicIpAddress': True,
            'Groups': [security_group_id]
         }],
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
    

    return instance_id, public_ip # Return the instance ID

def update_file(public_ip):
    # SSH Connection using Paramiko
    key_name= f'msys-infra-{region}-private-key'
    key_path = f'/home/ec2-user/python_boto3/{key_name}.pem'  # Replace with the path to your .pem file
    username = 'ubuntu'  # Replace with the username for your EC2 instance
    remote_file_path = '/etc/resolv.conf' 

    # Content to update in the remote file
    text_to_append = "This text will be appended to the file on the remote instance."
   

    # Create a new SSH client
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # Load the private key (.pem file)
        private_key = paramiko.RSAKey.from_private_key_file(key_path)

        # Connect to the remote server
        ssh_client.connect(hostname=public_ip, username=username, pkey=private_key)

        print("Connected to the remote server!")
        
        #Print content of the files before update
        command = f"cat {remote_file_path}"
        
        # Execute the command on the remote instance
        stdin, stdout, stderr = ssh_client.exec_command(command)
        print("Content Berfore Update: ")
        
        # Display the output (if any)
        for line in stdout:
            print(line.strip())

        command = f"echo '{text_to_append}' | sudo tee -a {remote_file_path}"
        # Execute the command on the remote instance
        stdin, stdout, stderr = ssh_client.exec_command(command)
        
        print("Appended Text: ")
        # Display the output (if any)
        for line in stdout:
            print(line.strip())

        #Print content of the files After update
        command = f"cat {remote_file_path}"
        
        # Execute the command on the remote instance
        stdin, stdout, stderr = ssh_client.exec_command(command)
        print("Content After Update: ")
        
        # Display the output (if any)
        for line in stdout:
            print(line.strip())        


        # Close the SSH connection
        ssh_client.close()
        print("SSH connection closed.")
    except Exception as e:
        print(f"Unable to connect or update file: {e}")

if __name__ == '__main__':
    # Usage example
    desired_vpc_name= f'msys-infra-{region}-vpc'  # Replace with desired VPC name
    desired_vpc_cidr = '10.0.0.0/16'  # Replace with desired VPC CIDR block
    desired_subnet_cidr = '10.0.1.0/24'  # Replace with desired subnet CIDR block

    created_vpc_id, created_subnet_id= create_vpc_igw_route_table_public_subnet(
        desired_vpc_name, desired_vpc_cidr, desired_subnet_cidr
    )
    print(f"VPC ID: {created_vpc_id}, Subnet ID: {created_subnet_id}")

    desired_group_name = f'msys-infra-{region}-sg'  # Replace with desired security group name
    desired_group_description = 'My Security Group Description'  # Replace with desired security group description
    desired_vpc_id = created_vpc_id  # Replace with your desired VPC ID

    existing_or_created_group_id = check_and_create_security_group(
        desired_group_name, desired_group_description, desired_vpc_id
    )

    instance_id,public_ip = launch_ec2_instance(created_vpc_id, created_subnet_id,existing_or_created_group_id)
    print(f"Launched EC2 instance with ID: {instance_id}")

    update_file(public_ip)