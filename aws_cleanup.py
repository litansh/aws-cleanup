# python aws_cleanup.py us-west-2 --ecr_days_old 30 --ebs_snapshot_days_old 30 --nat_gateway_threshold 1000 --ec2_cpu_threshold 20 --ec2_memory_threshold 20

import boto3
import argparse
from datetime import datetime, timedelta
from botocore.exceptions import NoCredentialsError, ClientError

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


def get_ec2_for_right_sizing(ec2, cloudwatch, cpu_threshold=20, memory_threshold=20):
    # List all EC2 instances
    instances = ec2.describe_instances()
    instances_for_sizing = []

    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']

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

            # Calculate the overall average of the CPU utilization
            avg_cpu_util = 0
            if cpu_metrics['Datapoints']:
                avg_cpu_util = sum(data_point['Average'] for data_point in cpu_metrics['Datapoints']) / len(cpu_metrics['Datapoints'])
                print("[Debug] Instance: {}, Average CPU Utilization: {}".format(instance_id, avg_cpu_util))
            else:
                print("[Debug] No relevant CPU Utilzation Metrics collected. Please check CloudWatch")

            # Check Memory utilization (assuming custom namespace and metric)
            memory_metrics = cloudwatch.get_metric_statistics(
                Namespace='AWS/EC2', # Replace with your actual namespace
                MetricName='MemoryUtilization',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=datetime.utcnow() - timedelta(days=7),
                EndTime=datetime.utcnow(),
                Period=86400,
                Statistics=['Average']
            )

            # Calculate the overall average of the Memory utilization
            avg_mem_util = 0
            if memory_metrics['Datapoints']:
                avg_mem_util = sum(data_point['Average'] for data_point in memory_metrics['Datapoints']) / len(memory_metrics['Datapoints'])
                print("[Debug] Instance: {}, Average Memory Utilization: {}".format(instance_id, avg_mem_util))
            else:
                print("[Debug] No relevant Memory Utilzation Metrics collected. Please check CloudWatch")

            # Compare against thresholds
            if avg_cpu_util < cpu_threshold or avg_mem_util < memory_threshold:
                instances_for_sizing.append(instance_id)

    return instances_for_sizing



def aws_cleanup(region, ecr_days_old, ebs_snapshot_days_old, nat_gateway_threshold, ec2_cpu_threshold, ec2_memory_threshold):
    try:
        ec2 = boto3.client('ec2', region_name=region)
        ecr = boto3.client('ecr', region_name=region)
        cloudwatch = boto3.client('cloudwatch', region_name=region)

        print("Checking for unattached EBS volumes...")
        unattached_volumes = list_unattached_ebs_volumes(ec2)
        print("Unattached EBS Volumes: {}".format(unattached_volumes))

        print("Checking for unused ECR repositories older than {} days...".format(ecr_days_old))
        unused_repos = list_unused_ecr_repositories(ecr)
        print("Unused ECR Repositories: {}".format(unused_repos))

        print("Checking for old EBS snapshots older than {} days...".format(ebs_snapshot_days_old))
        old_snapshots = list_old_ebs_snapshots(ec2, ebs_snapshot_days_old)
        print("Old EBS Snapshots: {}".format(old_snapshots))

        print("Checking for idle NAT Gateways...")
        idle_nats = get_idle_nat_gateways(ec2, cloudwatch, nat_gateway_threshold)
        print("Idle NAT Gateways: {}".format(idle_nats))

        print("Checking for EC2 instances to right size...")
        right_size_instances = get_ec2_for_right_sizing(ec2, cloudwatch, ec2_cpu_threshold, ec2_memory_threshold)
        print("EC2 Instances to Right Size: {}".format(right_size_instances))

    except NoCredentialsError:
        print("Error: AWS credentials not found.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean up AWS resources")
    parser.add_argument('region', help='The AWS region for resource cleanup')
    parser.add_argument('--ecr_days_old', type=int, default=30, help='Age in days to consider ECR repositories as unused')
    parser.add_argument('--ebs_snapshot_days_old', type=int, default=30, help='Age in days to consider EBS snapshots as old')
    parser.add_argument('--nat_gateway_threshold', type=int, default=1, help='Byte threshold for idle NAT Gateways')
    parser.add_argument('--ec2_cpu_threshold', type=int, default=20, help='CPU utilization threshold for right sizing EC2 instances')
    parser.add_argument('--ec2_memory_threshold', type=int, default=20, help='Memory utilization threshold for right sizing EC2 instances')
    args = parser.parse_args()

    aws_cleanup(args.region, args.ecr_days_old, args.ebs_snapshot_days_old, args.nat_gateway_threshold, args.ec2_cpu_threshold, args.ec2_memory_threshold)