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

def store_agent_info_to_ssm(ssm_client, launch_result, execution_role_arn=None):
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
    
    ssm_client.put_parameter(
        Name='/mcp_server/runtime_iam/ecr_repository_url',
        Value=f"https://{launch_result.ecr_repository_uri}",
        Type='String',
        Description='ECR Repository URL for MCP server',
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

class Config:
    """MCP Server 배포 설정"""
    REGION = "us-west-2"
    MCP_SERVER_NAME = "mcp_server_agentic_core_debug"



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
    
    # Check for execution role in configure response
    print(f"Configure response: {response}")
    if hasattr(response, 'execution_role_arn'):
        execution_role_arn = response.execution_role_arn
    elif hasattr(agentcore_runtime, 'execution_role_arn'):
        execution_role_arn = agentcore_runtime.execution_role_arn
    else:
        execution_role_arn = None
        print("Execution role ARN not found in response or runtime object")


    print("Launching MCP server to AgentCore Runtime...")
    print("This may take several minutes...")
    launch_result = agentcore_runtime.launch()
    print("Launch completed ✓")
    print(f"Agent ARN: {launch_result.agent_arn}")
    print(f"Agent ID: {launch_result.agent_id}")

    store_agent_info_to_ssm(ssm_client, launch_result, execution_role_arn)
    print("✓ Agent ARN, ID, ECR Repository URL, and Execution Role stored in Parameter Store")

    print("\nConfiguration stored successfully!")
    print(f"Agent ARN: {launch_result.agent_arn}")
    print(f"Agent ID: {launch_result.agent_id}")
    print(f"ECR Repository URL: https://{launch_result.ecr_repository_uri}")
    if execution_role_arn:
        print(f"Execution Role ARN: {execution_role_arn}")

if __name__ == "__main__":
    main()
