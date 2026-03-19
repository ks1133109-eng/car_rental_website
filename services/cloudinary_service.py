"""
Cloudinary image upload service for DriveX.
Falls back gracefully to base64 data URIs when Cloudinary is not configured.

KYC images are uploaded to a PRIVATE folder (drivex/kyc) with:
  - Access control: authenticated/signed URLs only
  - No public URL exposure
  - Stored as Cloudinary URL in DB instead of raw base64 (saves 90%+ DB space)
"""
import os
import uuid


def _is_configured():
    return all([
        os.environ.get('CLOUDINARY_CLOUD_NAME'),
        os.environ.get('CLOUDINARY_API_KEY'),
        os.environ.get('CLOUDINARY_API_SECRET'),
    ])


def _get_cloudinary():
    """Configure and return cloudinary module."""
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
        secure=True,
    )
    return cloudinary


ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/jpg'}
MAX_FILE_SIZE_BYTES = 8 * 1024 * 1024  # 8 MB


def upload_image(file_storage=None, base64_data=None, folder='drivex/cars'):
    """
    Upload a CAR image to Cloudinary (public access).

    Priority:
      1. file_storage  — a Werkzeug FileStorage object (from request.files)
      2. base64_data   — a raw data-URI string (from a hidden <input>)

    Returns the secure URL string, or None on failure.
    """
    if not _is_configured():
        # Dev fallback: return base64 as-is so local runs still work
        if base64_data and base64_data.startswith('data:image'):
            return base64_data
        return None

    try:
        cloudinary = _get_cloudinary()
        import cloudinary.uploader

        public_id = f"{folder}/{uuid.uuid4().hex}"

        if file_storage and file_storage.filename:
            mime = getattr(file_storage, 'content_type', '') or getattr(file_storage, 'mimetype', '')
            if mime and mime not in ALLOWED_MIME_TYPES:
                print(f"[Cloudinary] Blocked upload: invalid MIME type {mime}")
                return None
            result = cloudinary.uploader.upload(
                file_storage,
                public_id=public_id,
                overwrite=True,
                resource_type='image',
                transformation=[
                    {'width': 1200, 'height': 800, 'crop': 'fill', 'quality': 'auto:good'},
                ],
            )
            return result.get('secure_url')

        elif base64_data and base64_data.startswith('data:image'):
            result = cloudinary.uploader.upload(
                base64_data,
                public_id=public_id,
                overwrite=True,
                resource_type='image',
                transformation=[
                    {'width': 1200, 'height': 800, 'crop': 'fill', 'quality': 'auto:good'},
                ],
            )
            return result.get('secure_url')

    except Exception as e:
        print(f"[Cloudinary upload error] {e}")

    return None


def upload_kyc_image(base64_data=None, file_storage=None, doc_type='id'):
    """
    Upload a KYC document (Government ID or selfie) to Cloudinary.

    Security measures applied:
      - Stored in 'drivex/kyc' folder (separate from public car images)
      - type='authenticated' — images require a signed URL to view
      - Max resolution capped to prevent excessively large uploads
      - MIME type validated server-side
      - Falls back to base64 storage if Cloudinary is not configured (dev mode)

    Returns the secure URL string, or the original base64 if unconfigured.
    """
    if not _is_configured():
        # Dev fallback — store base64 directly (original behaviour)
        if base64_data and base64_data.startswith('data:image'):
            return base64_data
        return None

    try:
        cloudinary = _get_cloudinary()
        import cloudinary.uploader

        public_id = f"drivex/kyc/{doc_type}_{uuid.uuid4().hex}"

        upload_kwargs = dict(
            public_id     = public_id,
            overwrite     = True,
            resource_type = 'image',
            type          = 'authenticated',   # private — not publicly accessible
            transformation = [
                # Cap resolution — KYC docs don't need to be huge
                {'width': 1600, 'height': 1200, 'crop': 'limit', 'quality': 'auto:good'},
            ],
            tags          = ['kyc'],
        )

        if file_storage and file_storage.filename:
            mime = getattr(file_storage, 'content_type', '') or getattr(file_storage, 'mimetype', '')
            if mime and mime not in ALLOWED_MIME_TYPES:
                print(f"[Cloudinary KYC] Blocked: invalid MIME type {mime}")
                return None
            result = cloudinary.uploader.upload(file_storage, **upload_kwargs)
            return result.get('secure_url')

        elif base64_data and base64_data.startswith('data:image'):
            result = cloudinary.uploader.upload(base64_data, **upload_kwargs)
            return result.get('secure_url')

    except Exception as e:
        print(f"[Cloudinary KYC upload error] {e}")

    return None


def get_signed_kyc_url(cloudinary_url, expires_in_seconds=300):
    """
    Generate a time-limited signed URL for viewing a private KYC image.
    Used by the admin dashboard to temporarily view KYC docs.
    URL expires after `expires_in_seconds` (default 5 minutes).

    Returns a signed URL string, or the original URL if Cloudinary not configured.
    """
    if not cloudinary_url or not _is_configured():
        return cloudinary_url

    # If it's still a base64 string (dev mode), return as-is
    if cloudinary_url.startswith('data:image'):
        return cloudinary_url

    try:
        cloudinary = _get_cloudinary()
        import cloudinary.utils
        import time

        # Extract public_id from URL
        # URL format: https://res.cloudinary.com/{cloud}/image/authenticated/s--xxx--/{public_id}
        # We need to re-generate a fresh signed URL
        parts = cloudinary_url.split('/')
        # Find the version/public_id portion after 'authenticated'
        try:
            auth_idx = parts.index('authenticated')
            # public_id is everything after authenticated/s--sig--/
            # Skip the signature part (s--xxx--)
            public_id_parts = parts[auth_idx + 2:]  # skip 'authenticated' and sig
            public_id = '/'.join(public_id_parts)
            # Remove file extension for public_id
            if '.' in public_id.split('/')[-1]:
                public_id = public_id.rsplit('.', 1)[0]
        except (ValueError, IndexError):
            # Fallback: return original URL
            return cloudinary_url

        signed_url, _ = cloudinary.utils.cloudinary_url(
            public_id,
            type       = 'authenticated',
            sign_url   = True,
            expires_at = int(time.time()) + expires_in_seconds,
        )
        return signed_url

    except Exception as e:
        print(f"[Cloudinary signed URL error] {e}")
        return cloudinary_url
