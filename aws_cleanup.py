import boto3
import argparse
import json
from datetime import datetime, timedelta
from botocore.exceptions import NoCredentialsError, ClientError

# Function to load configuration from the JSON file
def load_configuration(environment):
    try:
        with open('config.json', 'r') as config_file:
            config_data = json.load(config_file)
            return config_data.get('environments', {}).get(environment, {})
    except Exception as e:
        print("Error loading configuration from file: {}".format(e))
        return {}

def list_unattached_ebs_volumes(ec2):
    try:
        volumes = ec2.describe_volumes(
            Filters=[{'Name': 'status', 'Values': ['available']}]
        )
        return [v['VolumeId'] for v in volumes['Volumes']]
    except ClientError as e:
        print("Error fetching unattached EBS volumes: {}".format(e))
        return []


def list_unused_ecr_repositories(ecr):
    try:
        repos = ecr.describe_repositories()
        unused_repos = []
        for repo in repos['repositories']:
            images = ecr.list_images(repositoryName=repo['repositoryName'])
            if not images['imageIds']:
                unused_repos.append(repo['repositoryName'])
        return unused_repos
    except ClientError as e:
        print("Error fetching unused ECR repositories: {}".format(e))
        return []


def list_old_ebs_snapshots(ec2, days_old):
    try:
        now = datetime.now()
        snapshots = ec2.describe_snapshots(OwnerIds=['self'])
        old_snapshots = []
        for snapshot in snapshots['Snapshots']:
            # Check if the snapshot is older than specified days
            if (now - snapshot['StartTime'].replace(tzinfo=None)).days > days_old:
                old_snapshots.append(snapshot['SnapshotId'])
        return old_snapshots
    except ClientError as e:
        print("Error fetching old EBS snapshots: {}".format(e))
        return []


def get_idle_nat_gateways(ec2, cloudwatch, threshold=1):
    # List all NAT Gateways
    nat_gateways = ec2.describe_nat_gateways()
    idle_nat_gateways = []

    for nat in nat_gateways['NatGateways']:
        nat_id = nat['NatGatewayId']

        # Check network traffic for the NAT Gateway
        metrics = cloudwatch.get_metric_statistics(
            Namespace='AWS/NATGateway',
            MetricName='BytesOutToDestination',
            Dimensions=[{'Name': 'NatGatewayId', 'Value': nat_id}],
            StartTime=datetime.utcnow() - timedelta(days=1),
            EndTime=datetime.utcnow(),
            Period=86400,
            Statistics=['Sum']
        )

        # Check if traffic is below the threshold
        if metrics['Datapoints']:
            total_bytes = metrics['Datapoints'][0]['Sum']
            if total_bytes < threshold:
                idle_nat_gateways.append(nat_id)

    return idle_nat_gateways


def get_ec2_for_right_sizing(ec2, cloudwatch, environment):
    # List all EC2 instances
    instances = ec2.describe_instances()
    instances_for_sizing = []

    # Create a set to store all skip_resize_type values
    skip_resize_set = set(environment['skip_resize_types'])

    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']

            # Check for labels
            labels = instance.get('Tags', [])

            # Initialize thresholds
            delete_threshold = 0
            resize_threshold = 0

            # Set thresholds based on labels
            for label in labels:
                if label.get('Key') in environment['label_policies']:
                    policy = environment['label_policies'][label.get('Key')]
                    delete_threshold = max(delete_threshold, policy.get('delete_threshold', 0))
                    resize_threshold = max(resize_threshold, policy.get('resize_threshold', 0))

            # Check if any label is in skip_resize_set
            if not any(label.get('Key') in skip_resize_set for label in labels):
                # Check CPU utilization
                cpu_metrics = cloudwatch.get_metric_statistics(
                    Namespace='AWS/EC2',
                    MetricName='CPUUtilization',
                    Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                    StartTime=datetime.utcnow() - timedelta(days=7),
                    EndTime=datetime.utcnow(),
                    Period=86400,
                    Statistics=['Average']
                )

                # Check Memory utilization (assuming custom namespace and metric)
                memory_metrics = cloudwatch.get_metric_statistics(
                    Namespace='AWS/EC2',  # Replace with your actual namespace
                    MetricName='MemoryUtilization',
                    Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                    StartTime=datetime.utcnow() - timedelta(days=7),
                    EndTime=datetime.utcnow(),
                    Period=86400,
                    Statistics=['Average']
                )

                # Calculate the overall average of the CPU utilization and Memory utilization
                avg_cpu_util = 0
                avg_mem_util = 0

                if cpu_metrics['Datapoints']:
                    avg_cpu_util = sum(data_point['Average'] for data_point in cpu_metrics['Datapoints']) / len(
                        cpu_metrics['Datapoints'])
                    print("[Debug] Instance: {}, Average CPU Utilization: {}".format(instance_id, avg_cpu_util))
                else:
                    print("[Debug] No relevant CPU Utilization Metrics collected. Please check CloudWatch")

                if memory_metrics['Datapoints']:
                    avg_mem_util = sum(data_point['Average'] for data_point in memory_metrics['Datapoints']) / len(
                        memory_metrics['Datapoints'])
                    print("[Debug] Instance: {}, Average Memory Utilization: {}".format(instance_id, avg_mem_util))
                else:
                    print("[Debug] No relevant Memory Utilization Metrics collected. Please check CloudWatch")

                # Compare against thresholds
                if avg_cpu_util < environment['ec2_cpu_threshold'] and avg_mem_util < environment['ec2_memory_threshold']:
                    instances_for_sizing.append(instance_id)
                    print("[Info] Resizing instance with ID: {}".format(instance_id))
                else:
                    print(
                        "[Info] Skipping instance with ID: {} (labeled as one of '{}' or doesn't meet thresholds)".format(
                            instance_id, skip_resize_set))

    return instances_for_sizing


def aws_cleanup(region, environment):
    try:
        ec2 = boto3.client('ec2', region_name=region)
        ecr = boto3.client('ecr', region_name=region)
        cloudwatch = boto3.client('cloudwatch', region_name=region)

        if environment['delete_ebs_snapshots']:
            print("Checking for unattached EBS volumes...")
            unattached_volumes = list_unattached_ebs_volumes(ec2)
            print("Unattached EBS Volumes: {}".format(unattached_volumes))

        if environment['delete_ecr']:
            print("Checking for unused ECR repositories older than {} days...".format(environment['ecr_days_old']))
            unused_repos = list_unused_ecr_repositories(ecr)
            print("Unused ECR Repositories: {}".format(unused_repos))

        if environment['delete_ebs_snapshots']:
            print("Checking for old EBS snapshots older than {} days...".format(environment['ebs_snapshot_days_old']))
            old_snapshots = list_old_ebs_snapshots(ec2, environment['ebs_snapshot_days_old'])
            print("Old EBS Snapshots: {}".format(old_snapshots))

        if environment['delete_nat_gateways']:
            print("Checking for idle NAT Gateways...")
            idle_nats = get_idle_nat_gateways(ec2, cloudwatch, environment['nat_gateway_threshold'])
            print("Idle NAT Gateways: {}".format(idle_nats))

        print("Checking for EC2 instances to right size...")
        right_size_instances = get_ec2_for_right_sizing(ec2, cloudwatch, environment)
        print("EC2 Instances to Right Size: {}".format(right_size_instances))

    except NoCredentialsError:
        print("Error: AWS credentials not found.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean up AWS resources")
    parser.add_argument('environment', help='The environment to use for resource cleanup (e.g., "ort2")')
    args = parser.parse_args()

    environment = load_configuration(args.environment)
    if not environment:
        print("Environment configuration not found.")
    else:
        region = environment.get('region')
        aws_cleanup(region, environment)
