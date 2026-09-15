import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
import os


def get_s3_client():
    try:
        # Initialize the S3 client
        s3_client = boto3.client('s3', region_name='us-east-1')  # Specify region if needed
        return s3_client
    except (NoCredentialsError, PartialCredentialsError) as e:
        raise RuntimeError("AWS credentials not found or incomplete") from e


def generate_signed_url(object_name: str, expiration: int = 3600):

    s3_client = get_s3_client()
    try:
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': os.getenv('AWS_BUCKET'), 'Key': object_name},
            ExpiresIn=expiration,
        )
        return response
    except Exception as e:
        raise RuntimeError(f'Failed to generate signed URL: {e}')
