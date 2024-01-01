import boto3
import json
# import random
import uuid
import os


def generate_fake_telegram_message(image_file_name):
    return {
        "message": {
            # "chat": {"id": random.randint(100000, 999999)},
            "chat": {"id": 5331485210},
            "photo": [{"file_id": str(uuid.uuid4())}],
            "image_name": image_file_name
        }
    }


def send_message_to_sqs(sqs_url, message, message_group_id):
    sqs = boto3.client('sqs')
    message_deduplication_id = str(uuid.uuid4())
    sqs.send_message(
        QueueUrl=sqs_url,
        MessageBody=json.dumps(message),
        MessageGroupId=message_group_id,
        MessageDeduplicationId=message_deduplication_id
    )


def lambda_handler(event, context):
    secrets_client = boto3.client('secretsmanager')
    secret_name = os.environ['CONFIG_SECRET_NAME']

    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response['SecretString'])
        sqs_url = secret['SQS_URL']
    except Exception as e:
        print(f"Error retrieving secret: {str(e)}")
        raise e

    image_file_name = "street.png"
    message_group_id = "lana"

    num_messages = 300
    for _ in range(num_messages):
        fake_message = generate_fake_telegram_message(image_file_name)
        send_message_to_sqs(sqs_url, fake_message, message_group_id)

    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully sent {num_messages} messages to SQS')
    }