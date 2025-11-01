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

# 공통 설정 및 shared 모듈 경로 추가
root_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(root_path))
sys.path.insert(0, str(root_path / "shared"))

from runtime_utils import create_agentcore_runtime_role

class Config:
    """MCP Server 배포 설정"""
    REGION = "us-west-2"
    MCP_SERVER_NAME = "mcp_server_agentic_core"



def main():
    boto_session = Session()
    region = boto_session.region_name
    
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


    print("Launching MCP server to AgentCore Runtime...")
    print("This may take several minutes...")
    launch_result = agentcore_runtime.launch()
    print("Launch completed ✓")
    print(f"Agent ARN: {launch_result.agent_arn}")
    print(f"Agent ID: {launch_result.agent_id}")


    agent_arn_response = ssm_client.put_parameter(
        Name='/mcp_server/runtime_iam/agent_arn',
        Value=launch_result.agent_arn,
        Type='String',
        Description='Agent ARN for MCP server with inbound auth',
        Overwrite=True
    )
    print("✓ Agent ARN stored in Parameter Store")

    print("\nConfiguration stored successfully!")
    print(f"Agent ARN: {launch_result.agent_arn}")

if __name__ == "__main__":
    main()

