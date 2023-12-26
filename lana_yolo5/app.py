import time
from pathlib import Path
from detect import run
import yaml
from loguru import logger
import boto3
import botocore
import json
import requests
from botocore.exceptions import BotoCoreError, ClientError
from decimal import Decimal


prediction_summary = ''
dbresponse = ''

secrets_manager_name = "lanabot_secrets"
region_name = "eu-west-2"

session = boto3.session.Session()
client = session.client(
    service_name='secretsmanager',
    region_name=region_name
)

try:
    get_secret_value_response = client.get_secret_value(
        SecretId=secrets_manager_name
    )
except ClientError as e:
    raise e
secrets = json.loads(get_secret_value_response['SecretString'])
TELEGRAM_TOKEN = secrets['TELEGRAM_TOKEN']
TELEGRAM_APP_URL = secrets['TELEGRAM_APP_URL']
images_bucket = secrets['BUCKET_NAME']
AWS_REGION = secrets['REGION']
s3_access_key = secrets['S3_ACCESS_KEY']
s3_secret_key = secrets['S3_SECRET_KEY']
OPENAI_API_KEY = secrets['OPENAI_API_KEY']
queue_name = secrets['SQS_URL']

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table_name = 'lanabot-dynamoDB'
table = dynamodb.Table(table_name)

sqs_client = boto3.client('sqs', region_name=AWS_REGION)
s3_client = boto3.client('s3', aws_access_key_id=s3_access_key, aws_secret_access_key=s3_secret_key)


with open("data/coco128.yaml", "r") as stream:
    names = yaml.safe_load(stream)['names']


def consume():
    global prediction_summary
    global dbresponse
    while True:

        response = sqs_client.receive_message(QueueUrl=queue_name, MaxNumberOfMessages=1, WaitTimeSeconds=5)

        if 'Messages' in response:
            message_body = response['Messages'][0]['Body']
            receipt_handle = response['Messages'][0]['ReceiptHandle']
            prediction_id = response['Messages'][0]['MessageId']
            logger.info(f"\n\n======== Received predction_id in yolo5 from telegram:{prediction_id} ==========\n\n")

            logger.info(f'prediction: {prediction_id}. start processing')

            message_json = json.loads(message_body)

            img_name = message_json.get('image_name')
            logger.info(f"\n\n====== Image name:{img_name}\n\n")
            chat_id = message_json.get('chat_id')
            original_img_path = f'{img_name}'

            try:
                s3_client.download_file(images_bucket, img_name, original_img_path)
            except botocore.exceptions.ClientError as lana_exception:
                if lana_exception.response['Error']['Code'] == "404":
                    logger.error("The image does not found")
                else:
                    logger.error(lana_exception)
                    raise

            logger.info(f'prediction: {prediction_id}/{original_img_path}. Download img completed')

            # Predicts the objects in the image
            run(
                weights='yolov5s.pt',
                data='data/coco128.yaml',
                source=original_img_path,
                project='static/data',
                name=prediction_id,
                save_txt=True
            )

            logger.info(f'prediction: {prediction_id}/{original_img_path}. done')

            # This is the path for the predicted image with labels
            # The predicted image typically includes bounding boxes drawn around the
            # detected objects, along with class labels and possibly confidence scores.
            predicted_img_path = Path(f'static/data/{prediction_id}/{original_img_path}')

            # TODO Uploads the predicted image (predicted_img_path) to S3
            #  (be careful not to override the original image).
            s3_prediction_img_path = f'{img_name.split(".")[0]}_prediction.jpg'
            try:
                s3_client.upload_file(str(predicted_img_path), images_bucket, s3_prediction_img_path)
            except Exception as lana_exception:
                logger.error(lana_exception)
                raise

            # Parse prediction labels and create a summary :-
            pred_summary_path = Path(f'static/data/{prediction_id}/labels/{original_img_path.split(".")[0]}.txt')
            if pred_summary_path.exists():

                with open(pred_summary_path) as f:
                    labels = f.read().splitlines()
                    labels = [line.split(' ') for line in labels]
                    # labels = [{
                    #     'class': names[int(l[0])],
                    #     'cx': float(l[1]),
                    #     'cy': float(l[2]),
                    #     'width': float(l[3]),
                    #     'height': float(l[4]),
                    # } for l in labels]
                    labels = [{
                        'class': names[int(l[0])],
                        'cx': Decimal(str(l[1])),
                        'cy': Decimal(str(l[2])),
                        'width': Decimal(str(l[3])),
                        'height': Decimal(str(l[4])),
                    } for l in labels]

                logger.info(f'prediction: {prediction_id}/{original_img_path}. prediction summary:\n\n{labels}')
                predicted_img_path = str(Path(f'static/data/{prediction_id}/{original_img_path}'))

                # prediction_summary = {
                #     'prediction_id': prediction_id,
                #     'chat_id': chat_id,
                #     'there_is_prediction': 'Yes',
                #     'original_img_path': original_img_path,
                #     'predicted_img_path': predicted_img_path,
                #     'labels': labels,
                #     'time': time.time()
                # }
                prediction_summary = {
                    'prediction_id': prediction_id,
                    'chat_id': chat_id,
                    'there_is_prediction': 'Yes',
                    'original_img_path': original_img_path,
                    'predicted_img_path': predicted_img_path,
                    'labels': labels,
                    'time': Decimal(str(time.time()))
                }
                dbresponse = table.put_item(Item=prediction_summary)
                logger.info(f"\n\n ======= Prediction_Id without Else:{prediction_id}")

            else:
                logger.info ("\n\n ELSE \n\n")
                # dbresponse = table.put_item(Item={
                #     'prediction_id': prediction_id,
                #     'chat_id': chat_id,
                #     'there_is_prediction': 'No',
                #     'original_img_path': '',
                #     'predicted_img_path': '',
                #     ' ': [{'class': "", 'cx': 0, 'cy': 0, 'width': 0, 'height': 0}],
                #     'time': time.time()
                # })

                prediction_summary = {
                    'prediction_id': prediction_id,
                    'chat_id': chat_id,
                    'there_is_prediction': 'No',
                    'original_img_path': '',
                    'predicted_img_path': '',
                    'labels': [{
                        'class': "",
                        'cx': Decimal('0'),
                        'cy': Decimal('0'),
                        'width': Decimal('0'),
                        'height': Decimal('0')
                    }],
                    'time': Decimal(str(time.time()))
                }

                dbresponse = table.put_item(Item=prediction_summary)
                logger.info(f"\n\n ======= Prediction_Id with Else:{prediction_id}")

            # time.sleep(45)
            sqs_client.delete_message(QueueUrl=queue_name, ReceiptHandle=receipt_handle)

            try:
                logger.info(f"\n\n ======= Prediction_Id before sending HTTP GET:{prediction_id}\n\n")
                if dbresponse.get('ResponseMetadata', {}).get('HTTPStatusCode') == 200:
                    logger.info("Data inserted successfully into DynamoDB.")

                    other_flask_server_url = TELEGRAM_APP_URL + "/results/"
                    params = {'predictionId': prediction_summary['prediction_id']}
                    # get_response = requests.get(other_flask_server_url, params=params)
                    get_response = requests.get(other_flask_server_url, params=params, verify=False)

                    if get_response.status_code == 200:
                        logger.info("GET request to Lanabot was successful.")
                        # logger.info("Response:", get_response.json())
                    else:
                        logger.info("GET request to Lanabot failed.")
                        # logger.info("Status Code:", get_response.status_code)

                else:
                    logger.info("Data insertion might have failed. Response:", dbresponse)

            except (BotoCoreError, ClientError, Exception) as error:
                logger.info(f"An error occurred: {error}")

if __name__ == "__main__":
    consume()
