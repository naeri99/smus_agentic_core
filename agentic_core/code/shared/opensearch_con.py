import json
import boto3
import requests
import asyncio
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
from langchain_aws import BedrockEmbeddings
from requests.auth import HTTPBasicAuth
from pathlib import Path
from opensearchpy import OpenSearch, RequestsHttpConnection

class OpenSearchEmbeddingProcessor:
    """OpenSearch 임베딩 처리 및 저장 클래스"""
    
    def __init__(self, region = 'us-west-2' ):
        # AWS region
        self.region = region
        self.service = 'es'
        
        # AWS credential
        self.session = boto3.Session()
        self.credentials = self.session.get_credentials()
        
        # OpenSearch setting
        secrets_client = boto3.client('secretsmanager', region_name=self.region)
        response = secrets_client.get_secret_value(SecretId='opensearch-credentials')
        secrets = json.loads(response['SecretString'])
        self.username = secrets['username']
        self.password = secrets['password'] 
        self.host = secrets['opensearch_host']
        self.headers = {'Content-Type': 'application/json'}
        
        # embedding
        self.embeddings = self._setup_embeddings()
        self.os_client = OpenSearch(
                            hosts=[{'host': self.host, 'port': 443}],
                            http_auth=(self.username, self.password),
                            use_ssl=True,
                            verify_certs=True,
                            connection_class=RequestsHttpConnection
                        )
        self.index_name = None


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

    def create_index(self, index_name, index_mapping):  
        self.index_name = index_name
        if self.os_client.indices.exists(index=index_name):
            print(f"Index {index_name} already exists")
        else:
            self.os_client.indices.create(index=index_name, body=index_mapping)
            print(f"Index {index_name} created successfully")

    def delete_index(self, index_name):
        if self.os_client.indices.exists(index=index_name):
            self.os_client.indices.delete(index=index_name)
            print(f"Index {index_name} deleted")
        else:
            print(f"Index {index_name} does not exist")


    def save_data(self, pk , document):
        try:
            response = self.os_client.index(
                index=self.index_name ,
                body=document,
                id=f"aws_doc_{pk}"
            )
            if pk % 50 ==0 :
                print(f"Document {pk} indexed successfully")
        except Exception as e:
            print(f"Error indexing document {pk}: {e}")

    def get_data_path(self):
        current_dir = Path.cwd()
        data_path = current_dir.parent.parent.parent.parent / "data" / "raw" / "basic_aws_dictionary.json"
        return str(data_path)

    def read_json(self,path ):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_embedding(self, text):
        """BedrockEmbeddings를 사용한 임베딩 생성"""
        if not self.embeddings:
            self.embeddings = self._setup_embeddings()
        
        return self.embeddings.embed_query(text)

    def get_embedding_with_key(self, data , key):
        """BedrockEmbeddings를 사용한 임베딩 생성"""
        if not self.embeddings:
            self.embeddings = self._setup_embeddings()
        
        return self.embeddings.embed_query(data[key])
    
    def get_embeddings_batch(self, texts):
        """여러 텍스트의 임베딩을 배치로 생성"""
        if not self.embeddings:
            self.embeddings = self._setup_embeddings()
        
        return self.embeddings.embed_documents(texts)

    def check_data_property(self, data):
        print("data -> ", data[0])
        print("*"*175)
        print("keys -> ", print(data[0].keys()))

    

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
    