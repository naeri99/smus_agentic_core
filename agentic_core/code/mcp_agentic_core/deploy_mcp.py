"""
deploy_mcp.py

MCP Server 배포 스크립트
ETF 데이터 조회용 MCP Server 배포
"""


import boto3
import sys
import time
import json
from pathlib import Path
from bedrock_agentcore_starter_toolkit import Runtime
from bedrock_agentcore_starter_toolkit.operations.runtime import destroy_bedrock_agentcore
from boto3.session import Session
from pathlib import Path
import os


# 공통 설정 및 shared 모듈 경로 추가
root_path = Path(__file__).parent.parent
print(root_path)
sys.path.insert(0, str(root_path))
sys.path.insert(0, str(root_path / "shared"))

from runtime_utils import create_agentcore_runtime_role

def store_agent_info_to_ssm(ssm_client, launch_result, execution_role_arn=None, ecr_repository_uri=None):
    """Store agent information to SSM Parameter Store"""
    ssm_client.put_parameter(
        Name='/mcp_server/runtime_iam/agent_arn',
        Value=launch_result.agent_arn,
        Type='String',
        Description='Agent ARN for MCP server',
        Overwrite=True
    )
    
    ssm_client.put_parameter(
        Name='/mcp_server/runtime_iam/agent_id',
        Value=launch_result.agent_id,
        Type='String',
        Description='Agent ID for MCP server',
        Overwrite=True
    )
    
    if execution_role_arn:
        ssm_client.put_parameter(
            Name='/mcp_server/runtime_iam/execution_role_arn',
            Value=execution_role_arn,
            Type='String',
            Description='Execution Role ARN for MCP server',
            Overwrite=True
        )
    
    if ecr_repository_uri:
        ssm_client.put_parameter(
            Name='/mcp_server/runtime_iam/ecr_repository_uri',
            Value=ecr_repository_uri,
            Type='String',
            Description='ECR Repository URI for MCP server',
            Overwrite=True
        )

class Config:
    """MCP Server 배포 설정"""
    REGION = "us-west-2"
    MCP_SERVER_NAME = "mcp_server_agentic_core_kkk"



def main():
    boto_session = Session()
    region = boto_session.region_name
    
    agentcore_control_client = boto_session.client("bedrock-agentcore-control", region_name=region)
    ssm_client = boto_session.client('ssm', region_name=region)
    
    
    print(f"Using AWS region: {region}")

    required_files = ["mcp_server.py", "requirements.txt"]
    for file in required_files:
        if not os.path.exists(file):
            raise FileNotFoundError(f"Required file {file} not found")
    print("All required files found ✓")

    agentcore_runtime = Runtime()

    print("Configuring AgentCore Runtime...")
    response = agentcore_runtime.configure(
        entrypoint="mcp_server.py",
        auto_create_execution_role=True,
        auto_create_ecr=True,
        requirements_file="requirements.txt",
        region=region,
        protocol="MCP",
        agent_name=Config.MCP_SERVER_NAME,
    )
    print("Configuration completed ✓")
    
    # Debug: Print all available attributes
    print(f"Response type: {type(response)}")
    print(f"Response attributes: {dir(response)}")
    if hasattr(response, '__dict__'):
        print(f"Response dict: {response.__dict__}")
    
    print(f"Runtime type: {type(agentcore_runtime)}")
    print(f"Runtime attributes: {dir(agentcore_runtime)}")
    if hasattr(agentcore_runtime, '__dict__'):
        print(f"Runtime dict: {agentcore_runtime.__dict__}")
    
    # Try to find execution role and ECR repository
    execution_role_arn = None
    ecr_repository_uri = None
    
    for attr in ['execution_role_arn', 'role_arn', 'iam_role_arn']:
        if hasattr(response, attr):
            execution_role_arn = getattr(response, attr)
            print(f"Found execution role in response.{attr}: {execution_role_arn}")
            break
        elif hasattr(agentcore_runtime, attr):
            execution_role_arn = getattr(agentcore_runtime, attr)
            print(f"Found execution role in runtime.{attr}: {execution_role_arn}")
            break
    
    for attr in ['ecr_repository_uri', 'repository_uri', 'ecr_uri']:
        if hasattr(response, attr):
            ecr_repository_uri = getattr(response, attr)
            print(f"Found ECR repository in response.{attr}: {ecr_repository_uri}")
            break
        elif hasattr(agentcore_runtime, attr):
            ecr_repository_uri = getattr(agentcore_runtime, attr)
            print(f"Found ECR repository in runtime.{attr}: {ecr_repository_uri}")
            break


    print("Launching MCP server to AgentCore Runtime...")
    print("This may take several minutes...")
    launch_result = agentcore_runtime.launch()
    print("Launch completed ✓")
    print(f"Agent ARN: {launch_result.agent_arn}")
    print(f"Agent ID: {launch_result.agent_id}")

    store_agent_info_to_ssm(ssm_client, launch_result, execution_role_arn, ecr_repository_uri)
    print("✓ Agent ARN, ID, Execution Role, and ECR Repository stored in Parameter Store")

    print("\nConfiguration stored successfully!")
    print(f"Agent ARN: {launch_result.agent_arn}")
    print(f"Agent ID: {launch_result.agent_id}")
    if execution_role_arn:
        print(f"Execution Role ARN: {execution_role_arn}")
    if ecr_repository_uri:
        print(f"ECR Repository URI: {ecr_repository_uri}")

if __name__ == "__main__":
    main()

