from .aws_s3 import get_s3_client, generate_signed_url
from fastapi import HTTPException
import os
from .procedures import generate_random_string
from PIL import Image
import io


def upload_file_s3(file):
    try:
        ext = file.filename.split('.')[-1]
        new_filename = '{}.{}'.format(generate_random_string(), ext)
        filepath = '{}/{}'.format('neuralagent_clients', new_filename)

        s3_client = get_s3_client()
        s3_client.upload_fileobj(
            file.file,
            os.getenv('AWS_BUCKET'),
            filepath
        )

        return filepath
    except Exception as e:
        return None


def upload_screenshot_s3_bytesio(buffer: io.BytesIO, extension="png"):
    try:
        new_filename = f"{generate_random_string()}.{extension}"
        filepath = f"neuralagent_screenshots/{new_filename}"

        s3_client = get_s3_client()
        s3_client.upload_fileobj(
            buffer,
            os.getenv('AWS_BUCKET'),
            filepath
        )

        return filepath
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {e}")


def generate_thumbnail(image_data, size):
    """
        Generate a thumbnail of the given size.

        :param image_data: Binary image data.
        :param size: Tuple (width, height) for the thumbnail.
        :return: BytesIO object containing the resized image.
        """
    image = Image.open(io.BytesIO(image_data))
    image.thumbnail(size)  # Resize the image while maintaining aspect ratio

    # Save thumbnail to a BytesIO object
    thumb_io = io.BytesIO()
    image.save(thumb_io, format=image.format)
    thumb_io.seek(0)
    return thumb_io


async def upload_image_s3(image):
    image_data = await image.read()
    thumb_sm = generate_thumbnail(image_data, (200, 200))
    thumb_lg = generate_thumbnail(image_data, (700, 700))

    ext = image.filename.split('.')[-1]
    random_string = generate_random_string()

    new_filename = '{}.{}'.format(random_string, ext)
    thumb_sm_name = '{}.thumb_sm.{}'.format(random_string, ext)
    thumb_lg_name = '{}.thumb_lg.{}'.format(random_string, ext)

    filepath = '{}/{}'.format('neuralagent_clients', new_filename)
    thumb_sm_path = '{}/{}'.format('neuralagent_clients', thumb_sm_name)
    thumb_lg_path = '{}/{}'.format('neuralagent_clients', thumb_lg_name)

    s3_client = get_s3_client()
    s3_client.upload_fileobj(
        image.file,
        os.getenv('AWS_BUCKET'),
        filepath
    )

    s3_client.upload_fileobj(
        thumb_sm,
        os.getenv('AWS_BUCKET'),
        thumb_sm_path
    )

    s3_client.upload_fileobj(
        thumb_lg,
        os.getenv('AWS_BUCKET'),
        thumb_lg_path
    )

    return filepath


def get_file_url(filepath):
    return generate_signed_url(filepath, 3600 * 3)


def construct_image_obj(image):
    ext = image.split('.')[-1]
    name = image.split('.')[0]

    image_path = '{}.{}'.format(name, ext)
    thumb_sm_path = '{}.thumb_sm.{}'.format(name, ext)
    thumb_lg_path = '{}.thumb_lg.{}'.format(name, ext)

    return {
        'original': get_file_url(image_path),
        'thumb_sm': get_file_url(thumb_sm_path),
        'thumb_lg': get_file_url(thumb_lg_path)
    }
