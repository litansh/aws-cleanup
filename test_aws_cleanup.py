import unittest
from unittest.mock import MagicMock, patch
from aws_cleanup import (
    list_unattached_ebs_volumes,
    list_unused_ecr_repositories,
    list_old_ebs_snapshots,
    get_idle_nat_gateways,
    get_ec2_for_right_sizing,
)

class TestAWSCleanup(unittest.TestCase):

    @patch('boto3.client')
    def test_list_unattached_ebs_volumes(self, mock_boto3_client):
        mock_ec2 = MagicMock()
        mock_boto3_client.return_value = mock_ec2

        mock_ec2.describe_volumes.return_value = {
            'Volumes': [
                {'VolumeId': 'vol-1', 'Status': 'available'},
                {'VolumeId': 'vol-2', 'Status': 'in-use'},
            ]
        }

        unattached_volumes = list_unattached_ebs_volumes(mock_ec2)
        self.assertEqual(unattached_volumes, ['vol-1'])

    @patch('boto3.client')
    def test_list_unused_ecr_repositories(self, mock_boto3_client):
        mock_ecr = MagicMock()
        mock_boto3_client.return_value = mock_ecr

        mock_ecr.describe_repositories.return_value = {
            'repositories': [
                {'repositoryName': 'repo-1'},
                {'repositoryName': 'repo-2'},
            ]
        }
        mock_ecr.list_images.return_value = {'imageIds': []}

        unused_repos = list_unused_ecr_repositories(mock_ecr)
        self.assertEqual(unused_repos, ['repo-1', 'repo-2'])

    @patch('boto3.client')
    def test_list_old_ebs_snapshots(self, mock_boto3_client):
        mock_ec2 = MagicMock()
        mock_boto3_client.return_value = mock_ec2

        mock_ec2.describe_snapshots.return_value = {
            'Snapshots': [
                {'SnapshotId': 'snap-1', 'StartTime': (datetime.now() - timedelta(days=31)).isoformat()},
                {'SnapshotId': 'snap-2', 'StartTime': (datetime.now() - timedelta(days=29)).isoformat()},
            ]
        }

        old_snapshots = list_old_ebs_snapshots(mock_ec2, days_old=30)
        self.assertEqual(old_snapshots, ['snap-1'])

    @patch('boto3.client')
    def test_get_idle_nat_gateways(self, mock_boto3_client):
        mock_ec2 = MagicMock()
        mock_cloudwatch = MagicMock()
        mock_boto3_client.side_effect = [mock_ec2, mock_cloudwatch]

        mock_ec2.describe_nat_gateways.return_value = {
            'NatGateways': [
                {'NatGatewayId': 'nat-1'},
                {'NatGatewayId': 'nat-2'},
            ]
        }
        mock_cloudwatch.get_metric_statistics.return_value = {
            'Datapoints': [{'Sum': 500}]
        }

        idle_nat_gateways = get_idle_nat_gateways(mock_ec2, mock_cloudwatch, threshold=1000)
        self.assertEqual(idle_nat_gateways, ['nat-1'])

    @patch('boto3.client')
    def test_get_ec2_for_right_sizing(self, mock_boto3_client):
        mock_ec2 = MagicMock()
        mock_cloudwatch = MagicMock()
        mock_boto3_client.side_effect = [mock_ec2, mock_cloudwatch]

        mock_ec2.describe_instances.return_value = {
            'Reservations': [
                {
                    'Instances': [
                        {
                            'InstanceId': 'instance-1',
                            'Tags': [{'Key': 'databases', 'Value': 'true'}],
                        },
                        {
                            'InstanceId': 'instance-2',
                            'Tags': [{'Key': 'web_servers', 'Value': 'true'}],
                        },
                        {
                            'InstanceId': 'instance-3',
                            'Tags': [{'Key': 'custom_label', 'Value': 'true'}],
                        },
                    ]
                }
            ]
        }

        mock_cloudwatch.get_metric_statistics.return_value = {
            'Datapoints': [{'Average': 10}]
        }

        instances_for_sizing = get_ec2_for_right_sizing(mock_ec2, mock_cloudwatch, cpu_threshold=20, memory_threshold=20)
        self.assertEqual(instances_for_sizing, ['instance-2', 'instance-3'])
