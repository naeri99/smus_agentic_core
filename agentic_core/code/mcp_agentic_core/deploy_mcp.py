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


class Config:
    """MCP Server 배포 설정"""
    REGION = "us-west-2"
    MCP_SERVER_NAME = "mcp_server_agentic_core_why"



# 공통 설정 및 shared 모듈 경로 추가
root_path = Path(__file__).parent.parent
print(root_path)
sys.path.insert(0, str(root_path))
sys.path.insert(0, str(root_path / "shared"))

from runtime_utils import create_agentcore_runtime_role

def add_ssm_permissions_to_execution_role(boto_session, execution_role_arn):
    """Add SSM permissions to execution role"""
    if not execution_role_arn:
        print("No execution role ARN provided, skipping SSM permissions")
        return
    
    # Get current account ID and region
    sts_client = boto_session.client('sts')
    account_id = sts_client.get_caller_identity()['Account']
    region = boto_session.region_name
    
    # Create IAM client
    iam_client = boto_session.client('iam')
    
    # Extract role name from ARN
    role_name = execution_role_arn.split('/')[-1]
    
    # SSM policy document
    ssm_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "ssm:*",
                "Resource": f"arn:aws:ssm:{region}:{account_id}:parameter/*"
            }
        ]
    }
    
    policy_name = "SSMParameterAccess"
    
    try:
        # Try to create inline policy
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(ssm_policy)
        )
        print(f"✓ Added SSM permissions to role {role_name}")
        print(f"  Account ID: {account_id}")
        print(f"  Region: {region}")
    except Exception as e:
        print(f"Failed to add SSM permissions: {e}")

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



def main():
    boto_session = Session()
    region = Config.REGION
    
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
    
    # Get execution role ARN from runtime after configuration
    execution_role_arn = None
    if hasattr(agentcore_runtime, 'execution_role_arn'):
        execution_role_arn = agentcore_runtime.execution_role_arn
        print(f"Found execution role ARN: {execution_role_arn}")
    elif hasattr(agentcore_runtime, '_execution_role_arn'):
        execution_role_arn = agentcore_runtime._execution_role_arn
        print(f"Found execution role ARN: {execution_role_arn}")
    
    # If not found, try IAM lookup with known pattern
    if not execution_role_arn:
        try:
            iam_client = boto_session.client('iam', region_name=region)
            # Try to find role with agent name pattern
            role_prefix = f"AmazonBedrockAgentCoreSDKRuntime-{region}-"
            paginator = iam_client.get_paginator('list_roles')
            for page in paginator.paginate():
                for role in page['Roles']:
                    if role['RoleName'].startswith(role_prefix):
                        execution_role_arn = role['Arn']
                        print(f"Found execution role via IAM search: {execution_role_arn}")
                        break
                if execution_role_arn:
                    break
        except Exception as e:
            print(f"Could not find execution role: {e}")
    
    # Initialize ECR repository URI
    ecr_repository_uri = None


    print("Launching MCP server to AgentCore Runtime...")
    print("This may take several minutes...")
    
    # Capture stdout to parse execution role from logs
    import sys
    from io import StringIO
    
    old_stdout = sys.stdout
    captured_output = StringIO()
    sys.stdout = captured_output
    
    try:
        launch_result = agentcore_runtime.launch()
    finally:
        sys.stdout = old_stdout
    
    # Parse execution role from captured output
    output_lines = captured_output.getvalue()
    print(output_lines)  # Print the captured output
    
    for line in output_lines.split('\n'):
        if "✅ Execution role available:" in line:
            execution_role_arn = line.split("✅ Execution role available: ")[1].strip()
            print(f"Found execution role from logs: {execution_role_arn}")
            break
    print("Launch completed ✓")
    print(f"Agent ARN: {launch_result.agent_arn}")
    print(f"Agent ID: {launch_result.agent_id}")

    # Extract ECR repository URI from launch result
    if hasattr(launch_result, 'ecr_uri') and launch_result.ecr_uri:
        ecr_repository_uri = launch_result.ecr_uri
        print(f"Found ECR URI in launch_result: {ecr_repository_uri}")

    # Add SSM permissions to execution role
    add_ssm_permissions_to_execution_role(boto_session, execution_role_arn)

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

