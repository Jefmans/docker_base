from minio import Minio
from minio.error import S3Error


def get_minio_client() -> Minio:
    return Minio(
        "minio:9000",
        access_key="minioadmin",
        secret_key="minioadmin123",
        secure=False,
    )


def ensure_bucket_exists(client: Minio, bucket_name: str) -> None:
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)


def remove_object_if_exists(client: Minio, bucket_name: str, object_name: str) -> bool:
    if not object_name or not client.bucket_exists(bucket_name):
        return False

    try:
        client.stat_object(bucket_name, object_name)
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            return False
        raise

    client.remove_object(bucket_name, object_name)
    return True
