from google.cloud import storage
import os
import json

# Path to service account key
key_path = "key/uet-education-qa-data-for-sft-e1a2fc9a3a71.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path

def check_gcs_access():
    try:
        # Initialize client
        storage_client = storage.Client()
        
        # Try to list buckets
        print("Đang kiểm tra quyền truy cập GCS...")
        buckets = list(storage_client.list_buckets())
        
        print("\nDanh sách các Bucket hiện có:")
        if not buckets:
            print("- Chưa có bucket nào.")
        for bucket in buckets:
            print(f"- {bucket.name}")
            
        return True
    except Exception as e:
        print(f"\nLỗi truy cập GCS: {e}")
        print("\nService account có thể chưa được cấp quyền 'Storage Admin' hoặc 'Storage Object Admin'.")
        return False

if __name__ == "__main__":
    check_gcs_access()
