import os
import json
from pathlib import Path
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.constants import StrategyType
from botocore.exceptions import ClientError
import logging
from use_memory_time import Config


client = None



shortterm_memory_id = Config.MEMORY_PREFIX

def initialize_memory_client():
    """Initialize the AgentCore Memory client"""
    global client
    
    try:
        client = MemoryClient(region_name="us-west-2")
        return True
    except Exception as e: 
        print(e)
        return False

def test_memory_connectivity():
    """Test basic AgentCore Memory connectivity"""
    if client is None:
        print("❌ Memory client is not initialized")
        return False

    try:
        print("🔍 Testing memory connectivity...")
        memories = client.list_memories()
        print(f"✅ Connected successfully. Found {len(memories)} existing memories.")
        return True
    except Exception as e: 
        print(f"❌ Connection failed: {e}")
        return False

def create_shortterm():
    """
    Creates short-term memory resource.
    This memory resource stores raw conversation history for context retrieval.
    """
    global shortterm_memory_id
    memory_name = "agentic_memory"
    
    try:
        print(f"📝 Creating short-term memory... ")
        shortterm_memory = client.create_memory_and_wait(
            name=memory_name,
            description="Short-term memory for conversation context",
            strategies=[],
            event_expiry_days=7
        )
        shortterm_memory_id = shortterm_memory["id"]
        print(f"✅ Short-term memory created successfully with ID: {shortterm_memory_id}")
        return True

    except ClientError as e: 
        if e.response.get('Error', {}).get('Code') == 'ValidationException' and "already exists" in str(e):
            memories = client.list_memories()
            # Find memory by checking if the name is in the ARN
            shortterm_memory_id = next((
                m.get('id') for m in memories 
                if memory_name in m.get('arn', '')
            ), None)
            
            if shortterm_memory_id:
                print(f"Memory already exists. Using existing memory ID: {shortterm_memory_id}")
                return True
            else:
                print(f"❌ Could not find existing memory with name: {memory_name}")
                return False
    except Exception as e:
        print(f"❌ Error creating short-term memory: {e}")
        return False

def save_deployment_info():
    """Save memory deployment information to JSON file"""
    if shortterm_memory_id:
        try:
            memory_details = client.get_memory(memoryId=shortterm_memory_id)
            deployment_info = {
                "memory_id": shortterm_memory_id
            }
            
            with open("deployment_info.json", "w") as f:
                json.dump(deployment_info, f, indent=2)
            
            print(f"✅ Deployment info saved: {deployment_info}")
            return True
        except Exception as e:
            print(f"❌ Error saving deployment info: {e}")
            return False
    return False

# Initialize client and create memory
if initialize_memory_client():
    if test_memory_connectivity():
        if create_shortterm():
            save_deployment_info()
