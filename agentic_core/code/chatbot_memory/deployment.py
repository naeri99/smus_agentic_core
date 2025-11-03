"""
deploy.py
"""

import sys
import time
import json
from pathlib import Path
from bedrock_agentcore_starter_toolkit import Runtime
from boto3.session import Session

# # 공통 설정 및 shared 모듈 경로 추가
root_path = Path(__file__).parent.parent
sys.path.insert(0, str(root_path))
sys.path.insert(0, str(root_path / "shared"))

from runtime_utils import create_agentcore_runtime_role



class Config:
    """chatbot llm 배포 설정"""
    REGION = "us-west-2"
    AGENT_NAME = "chatbot_llm_final"  # 하이픈을 언더스코어로 변경



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
            },
            {
                "Effect": "Allow",
                "Action": "dynamodb:*",
                "Resource": "*"
            }
        ]
    }
    
    policy_name = "SSMParameterAccessChatbot"
    
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


def deploy_chatbot_llm():
    """chatbot-llm 배포"""
    print("🎯 chatbot-lln 배포 중...")
    boto_session = Session()
    # IAM 역할 생성
    iam_role = create_agentcore_runtime_role(Config.AGENT_NAME, Config.REGION)
    iam_role_name = iam_role['Role']['RoleName']
    
    
    # Runtime 구성
    current_dir = Path(__file__).parent
    runtime = Runtime()
    runtime.configure(
        entrypoint=str(current_dir / "chatbot_agenticCore.py"),
        execution_role=iam_role['Role']['Arn'],
        auto_create_ecr=True,
        requirements_file=str(current_dir / "requirements.txt"),
        region=Config.REGION,
        agent_name=Config.AGENT_NAME
    )

    
    
    # 배포 실행
    launch_result = runtime.launch(auto_update_on_conflict=True)
    
    # 배포 완료 대기
    for i in range(30):
        try:
            status = runtime.status().endpoint['status']
            print(f"📊 상태: {status} ({i*30}초 경과)")
            if status in ['READY', 'CREATE_FAILED', 'DELETE_FAILED', 'UPDATE_FAILED']:
                break
        except Exception as e:
            print(f"⚠️ 상태 확인 오류: {e}")
        time.sleep(30)
    
    if status != 'READY':
        raise Exception(f"배포 실패: {status}")
    
    # ECR 리포지토리 이름 추출
    ecr_repo_name = None
    if hasattr(launch_result, 'ecr_uri') and launch_result.ecr_uri:
        ecr_repo_name = launch_result.ecr_uri.split('/')[-1].split(':')[0]
    
    add_ssm_permissions_to_execution_role(boto_session, iam_role['Role']['Arn'])

    
    return {
        "agent_arn": launch_result.agent_arn,
        "agent_id": launch_result.agent_id,
        "region": Config.REGION,
        "iam_role_name": iam_role_name,
        "ecr_repo_name": ecr_repo_name
    }



def save_deployment_info(analyst_info):
    """배포 정보 저장"""
    deployment_info = {
        "agent_name": Config.AGENT_NAME,
        "agent_arn": analyst_info["agent_arn"],
        "agent_id": analyst_info["agent_id"],
        "region": Config.REGION,
        "iam_role_name": analyst_info["iam_role_name"],
        "ecr_repo_name": analyst_info.get("ecr_repo_name"),
        "deployed_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    info_file = Path(__file__).parent / "deployment_info.json"
    with open(info_file, 'w') as f:
        json.dump(deployment_info, f, indent=2)
    
    return str(info_file)

def main():
    boto_session = Session()
    region = Config.REGION
    
    agentcore_control_client = boto_session.client("bedrock-agentcore-control", region_name=region)
    ssm_client = boto_session.client('ssm', region_name=region)
    
    try:
        print("🎯Analyst Runtime 배포")
        
        # Financial Analyst 배포
        analyst_info = deploy_chatbot_llm()
        
        # 배포 정보 저장
        info_file = save_deployment_info(analyst_info)
        
        print(f"\n🎉 배포 완료!")
        print(f"📄 배포 정보: {info_file}")
        print(f"🔗 Financial Analyst ARN: {analyst_info['agent_arn']}")
        
        return 0
        
    except Exception as e:
        print(f"❌ 배포 실패: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())




