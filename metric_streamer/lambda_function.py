import boto3
import json
import os

def lambda_handler(event, context):
    secrets_client = boto3.client('secretsmanager')
    secret_name = os.environ['CONFIG_SECRET_NAME']

    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])

        QUEUE_URL = secret['SQS_URL']
        AUTOSCALING_GROUP_NAME = secret['AUTOSCALING_GROUP_NAME']
        CLOUDWATCH_NAMESPACE = secret['CLOUDWATCH_NAMESPACE']

    except Exception as e:
        print(f"Error retrieving secret: {str(e)}")
        raise e

    sqs_client = boto3.client('sqs')
    asg_client = boto3.client('autoscaling')
    cloudwatch_client = boto3.client('cloudwatch')

    queue_attrs = sqs_client.get_queue_attributes(
        QueueUrl=QUEUE_URL,
        AttributeNames=['ApproximateNumberOfMessages']
    )
    msgs_in_queue = int(queue_attrs['Attributes']['ApproximateNumberOfMessages'])

    asg_response = asg_client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[AUTOSCALING_GROUP_NAME]
    )
    asg_size = asg_response['AutoScalingGroups'][0]['DesiredCapacity']

    backlog_per_instance = msgs_in_queue / asg_size if asg_size > 0 else 0

    cloudwatch_client.put_metric_data(
        Namespace=CLOUDWATCH_NAMESPACE,
        MetricData=[
            {
                'MetricName': 'BacklogPerInstance',
                'Dimensions': [
                    {
                        'Name': 'AutoScalingGroupName',
                        'Value': AUTOSCALING_GROUP_NAME
                    },
                ],
                'Value': backlog_per_instance,
                'Unit': 'Count'
            },
        ]
    )

    return {
        'statusCode': 200,
        'body': f'Successfully sent backlog per instance metric: {backlog_per_instance}'
    }