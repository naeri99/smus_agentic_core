import boto3
import json
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth

class OpenSearchSecretsManager:
    """Secrets Manager를 사용한 OpenSearch 연결 관리자"""
    
    def __init__(self, secret_name="opensearch-credentials", region_name="us-west-2"):
        self.secret_name = secret_name
        self.region_name = region_name
        self.secrets_client = boto3.client('secretsmanager', region_name=region_name)
        self.credentials = self._get_credentials()
        
    def _get_credentials(self):
        """Secrets Manager에서 자격증명 가져오기"""
        try:
            response = self.secrets_client.get_secret_value(SecretId=self.secret_name)
            secret_string = response['SecretString']
            return json.loads(secret_string)
        except Exception as e:
            print(f"❌ Secrets Manager에서 자격증명을 가져오는데 실패: {e}")
            return None
    
    def get_opensearch_client(self):
        """OpenSearch 클라이언트 생성"""
        if not self.credentials:
            return None
            
        try:
            # HTTP 기본 인증 사용
            client = OpenSearch(
                hosts=[{
                    'host': self.credentials['opensearch_host'],
                    'port': 443
                }],
                http_auth=(
                    self.credentials['username'], 
                    self.credentials['password']
                ),
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection
            )
            
            # 연결 테스트
            info = client.info()
            print(f"✅ OpenSearch 연결 성공: {info['version']['number']}")
            return client
            
        except Exception as e:
            print(f"❌ OpenSearch 연결 실패: {e}")
            return None
    
    def get_credentials_dict(self):
        """자격증명 딕셔너리 반환"""
        return self.credentials
    
    @property
    def username(self):
        return self.credentials.get('username') if self.credentials else None
    
    @property
    def password(self):
        return self.credentials.get('password') if self.credentials else None
    
    @property
    def host(self):
        return self.credentials.get('opensearch_host') if self.credentials else None

# 사용 예제
def main():
    # Secrets Manager에서 자격증명 가져오기
    opensearch_manager = OpenSearchSecretsManager()
    
    # 자격증명 확인
    print("📋 OpenSearch 자격증명:")
    print(f"   Username: {opensearch_manager.username}")
    print(f"   Password: {'*' * len(opensearch_manager.password) if opensearch_manager.password else None}")
    print(f"   Host: {opensearch_manager.host}")
    
    # OpenSearch 클라이언트 생성
    client = opensearch_manager.get_opensearch_client()
    
    if client:
        # 간단한 테스트
        try:
            # 인덱스 목록 가져오기
            indices = client.cat.indices(format='json')
            print(f"📊 사용 가능한 인덱스: {len(indices)}개")
            
            # 클러스터 상태 확인
            health = client.cluster.health()
            print(f"🏥 클러스터 상태: {health['status']}")
            
        except Exception as e:
            print(f"❌ OpenSearch 작업 실패: {e}")

if __name__ == "__main__":
    main()