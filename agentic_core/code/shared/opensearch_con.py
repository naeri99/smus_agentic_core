import json
import boto3
import requests
import asyncio
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
from langchain_aws import BedrockEmbeddings
from requests.auth import HTTPBasicAuth

class OpenSearchEmbeddingProcessor:
    """OpenSearch 임베딩 처리 및 저장 클래스"""
    
    def __init__(self, region = 'us-west-2' ):
        # AWS 설정
        self.region = region
        self.service = 'es'
        
        # AWS 자격 증명 설정
        self.session = boto3.Session()
        self.credentials = self.session.get_credentials()
        
        # OpenSearch 설정
        secrets_client = boto3.client('secretsmanager', region_name=self.region)
        response = secrets_client.get_secret_value(SecretId='opensearch-credentials')
        secrets = json.loads(response['SecretString'])
        self.username = secrets['username']
        self.password = secrets['password'] 
        self.host = secrets['opensearch_host']
        self.headers = {'Content-Type': 'application/json'}
        
        # 임베딩 모델 초기화
        self.embeddings = self._setup_embeddings()
        
        # 인덱스 설정
        self.index_name = 'aws-chunks-enhanced'
        
    def _setup_embeddings(self):
        """Bedrock 임베딩 모델 설정"""
        try:
            return BedrockEmbeddings(
                client=boto3.client(
                    service_name='bedrock-runtime',
                    region_name=self.region
                ),
                model_id="amazon.titan-embed-text-v2:0"
            )
        except Exception as e:
            print(f"❌ 임베딩 모델 초기화 실패: {e}")
            return None


    def check_connection(self):
        """OpenSearch 연결 상태 확인"""
        try:
            url = f"https://{self.host}/_cluster/health"
            response = requests.get(
                url,
                auth=HTTPBasicAuth(self.username, self.password),
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                health = response.json()
                print(f"✅ OpenSearch 연결 성공")
                print(f"클러스터 상태: {health.get('status', 'unknown')}")
                return True
            else:
                print(f"❌ 연결 실패: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ 연결 오류: {e}")
            return False
    