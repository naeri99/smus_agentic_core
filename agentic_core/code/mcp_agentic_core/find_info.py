import boto3

def get_agent_info_from_ssm():
    """Retrieve and print agent information from SSM Parameter Store"""
    ssm_client = boto3.client('ssm')
    
    parameters = [
        '/mcp_server/runtime_iam/agent_arn',
        '/mcp_server/runtime_iam/agent_id',
        '/mcp_server/runtime_iam/execution_role_arn',
        '/mcp_server/runtime_iam/ecr_repository_uri'
    ]
    
    for param_name in parameters:
        try:
            response = ssm_client.get_parameter(Name=param_name)
            print(f"{param_name}: {response['Parameter']['Value']}")
        except ssm_client.exceptions.ParameterNotFound:
            print(f"{param_name}: Not found")

if __name__ == "__main__":
    get_agent_info_from_ssm()
