import boto3
import sys

region = sys.argv[1]

def cleanup_instance_and_security_group_by_tags(instance_name):
    ec2 = boto3.client('ec2', region_name= region)

    # Find the instance by its name tag
    response = ec2.describe_instances(Filters=[{'Name': 'tag:Name', 'Values': [instance_name]}])

    instance_id = None

    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']


    if instance_id:
        # Terminate the instance
        ec2.delete_tags(Resources=[instance_id], Tags=[{'Key': 'Name'}])
        ec2.terminate_instances(InstanceIds=[instance_id])
        print(f"Instance {instance_id} is terminating...")

        # Wait for termination (optional)
        waiter = ec2.get_waiter('instance_terminated')
        waiter.wait(InstanceIds=[instance_id])

    else:
        print(f"No Instance found with the name {instance_name}.")

 # Describe security groups with a specific tag
    response = ec2.describe_security_groups(Filters=[
        {
            'Name': 'group-name',
            'Values': [f'msys-infra-{region}-sg']
        }
    ])

    # Check if any security groups were found
    if 'SecurityGroups' in response:
        for sg in response['SecurityGroups']:
            sg_id = sg['GroupId']

            # Delete the security group
            ec2.delete_security_group(GroupId=sg_id)
            print(f"Security Group {sg_id} deleted.")
    else:
        print("No security groups found with the specified tag.")

def delete_vpc_by_name_tag(vpc_name):
    ec2 = boto3.client('ec2',region_name= region)

    # Find VPCs with the specified name tag
    response = ec2.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}])

    if 'Vpcs' in response and len(response['Vpcs']) > 0:
        vpc_id = response['Vpcs'][0]['VpcId']  # Assuming there's only one VPC with this name

        # Delete all resources attached to the VPC (subnets, internet gateways, etc.) before deletion

                # Deleting subnets associated with the VPC
        subnets = ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        for subnet in subnets['Subnets']:
            ec2.delete_subnet(SubnetId=subnet['SubnetId'])

        # Detach and delete internet gateways attached to the VPC
        internet_gateways = ec2.describe_internet_gateways(Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}])
        for ig in internet_gateways['InternetGateways']:
            ec2.detach_internet_gateway(InternetGatewayId=ig['InternetGatewayId'], VpcId=vpc_id)
            ec2.delete_internet_gateway(InternetGatewayId=ig['InternetGatewayId'])

        # Deleting route tables associated with the VPC (except the main route table)
        route_tables = ec2.describe_route_tables(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        
        for rt in route_tables['RouteTables']:
            
            if rt.get('Associations')==[]:
                # ec2.disassociate_route_table(AssociationId=association['RouteTableAssociationId'])
                ec2.delete_route_table(RouteTableId=rt['RouteTableId'])

        # # Deleting security groups associated with the VPC
        # security_groups = ec2.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        # for sg in security_groups['SecurityGroups']:
        #     ec2.delete_security_group(GroupId=sg['GroupId'])


        # Delete the VPC
        ec2.delete_vpc(VpcId=vpc_id)
        print(f"VPC {vpc_id} with the name '{vpc_name}' has been deleted with all its Dependencies.")
    else:
        print(f"No VPC found with the name '{vpc_name}'.")

def main(region):
    # Specify the name tag of the instance you want to clean up
    instance_name_to_cleanup = f'msys-infra-{region}-vm'

    cleanup_instance_and_security_group_by_tags(instance_name_to_cleanup)

    # Specify the name tag of the VPC you want to delete
    vpc_name_to_delete = f'msys-infra-{region}-vpc'

    delete_vpc_by_name_tag(vpc_name_to_delete)

if __name__ == '__main__' :
    
    All=['us-east-1', 'us-east-2', 'us-west-1', 'us-west-2']
    
    if region in All:
        print(f"Cleaning Resources for '{region}'...")
        main(region)
    
    elif region== 'all':
        for region in All:
            print(f"Cleaning Resources for '{region}'...")
            main(region)