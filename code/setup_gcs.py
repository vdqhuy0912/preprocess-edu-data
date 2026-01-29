from google.cloud import storage
import os
import json

key_path = "key/uet-education-qa-data-for-sft-e1a2fc9a3a71.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path

def create_bucket_if_not_exists(bucket_name):
    try:
        storage_client = storage.Client()
        
        # Check if bucket exists
        bucket = storage_client.bucket(bucket_name)
        if bucket.exists():
            print(f"Bucket '{bucket_name}' đã tồn tại.")
            return bucket.name
            
        # Create new bucket
        new_bucket = storage_client.create_bucket(bucket_name, location="us-central1")
        print(f"Đã tạo bucket mới: {new_bucket.name}")
        return new_bucket.name
        
    except Exception as e:
        print(f"Lỗi khi tạo/kiểm tra bucket: {e}")
        return None

if __name__ == "__main__":
    # Get project id from key file
    with open(key_path) as f:
        sa = json.load(f)
        project_id = sa['project_id']
    
    bucket_name = f"{project_id}-batch-processing"
    print(f"Thử tạo bucket: {bucket_name}")
    create_bucket_if_not_exists(bucket_name)
