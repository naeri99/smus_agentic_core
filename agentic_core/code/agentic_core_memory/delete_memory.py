from bedrock_agentcore.memory import MemoryClient
import json
import os
import time

# Load and delete memory
with open('deployment_info.json', 'r') as f:
    data = json.load(f)
    memory_id = data['memory_id']

client = MemoryClient(region_name='us-west-2')
client.delete_memory(memory_id=memory_id)

# Wait until memory is deleted
print(f"Waiting for memory {memory_id} to be deleted...")
while True:
    try:
        client.get_memory(memory_id=memory_id)
        print("Memory still exists, waiting...")
        time.sleep(5)
    except Exception as e:
        if "not found" in str(e).lower() or "does not exist" in str(e).lower():
            break
        print(f"Unexpected error: {e}")
        time.sleep(2)

print(f"Deleted memory: {memory_id}")
os.remove('deployment_info.json')
print("Deleted deployment_info.json")