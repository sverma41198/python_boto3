import boto3
import sys

region = sys.argv[1]

def delete_key_pair_by_name(key_pair_name):
    ec2 = boto3.client('ec2', region_name=region)

    try:
        ec2.delete_key_pair(KeyName=key_pair_name)
        print(f"Key pair '{key_pair_name}' deleted successfully.")
    except ec2.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'InvalidKeyPair.NotFound':
            print(f"The key pair '{key_pair_name}' does not exist.")
        else:
            print(f"An error occurred while deleting the key pair '{key_pair_name}': {e}")

# Specify the name of the key pair you want to delete
key_pair_name_to_delete = f'msys-infra-{region}-private-key'

delete_key_pair_by_name(key_pair_name_to_delete)
