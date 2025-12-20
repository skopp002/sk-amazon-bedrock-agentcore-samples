#!/usr/bin/env python3
"""
Cognito Setup for Health Lakehouse Data
Creates User Pool, App Client, Resource Server, and test users with OAuth scopes
Writes configuration to SSM Parameter Store
"""
import boto3
import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, Optional

class CognitoSetup:
    def __init__(self, region: str):
        self.cognito = boto3.client('cognito-idp', region_name=region)
        self.region = region
        self.env_file = Path(__file__).parent.parent / '.env'

    def find_existing_user_pool(self, pool_name: str) -> Optional[str]:
        """Find existing user pool by name."""
        try:
            paginator = self.cognito.get_paginator('list_user_pools')
            for page in paginator.paginate(MaxResults=60):
                for pool in page.get('UserPools', []):
                    if pool['Name'] == pool_name:
                        print(f"ℹ️  Found existing User Pool: {pool['Id']}")
                        return pool['Id']
        except Exception as e:
            print(f"⚠️  Error searching for user pool: {e}")
        return None

    def get_user_pool_client(self, user_pool_id: str, client_name: str) -> Optional[Dict]:
        """Get existing app client by name."""
        try:
            paginator = self.cognito.get_paginator('list_user_pool_clients')
            for page in paginator.paginate(UserPoolId=user_pool_id, MaxResults=60):
                for client in page.get('UserPoolClients', []):
                    if client['ClientName'] == client_name:
                        # Get full client details including secret
                        full_client = self.cognito.describe_user_pool_client(
                            UserPoolId=user_pool_id,
                            ClientId=client['ClientId']
                        )
                        print(f"ℹ️  Found existing App Client: {client['ClientId']}")
                        return full_client['UserPoolClient']
        except Exception as e:
            print(f"⚠️  Error searching for app client: {e}")
        return None

    def get_user_pool_domain(self, user_pool_id: str) -> Optional[str]:
        """Get existing domain for user pool."""
        try:
            response = self.cognito.describe_user_pool(UserPoolId=user_pool_id)
            domain = response['UserPool'].get('Domain')
            if domain:
                domain_url = f'https://{domain}.auth.{self.region}.amazoncognito.com'
                print(f"ℹ️  Found existing domain: {domain_url}")
                return domain_url
        except Exception as e:
            print(f"⚠️  Error getting domain: {e}")
        return None

    def write_to_env(self, config: Dict):
        """
        Write configuration to .env file.
        
        Note: This function is deprecated and will be removed in a future version.
        Configuration should be managed through SSM Parameter Store.
        This is kept temporarily for backward compatibility during migration.
        """
        print(f"⚠️  Warning: .env file updates are deprecated. Please migrate to SSM Parameter Store.")
        print(f"   Run: python ../ssm_migrate.py --migrate")
        
        try:
            # Read existing .env file
            env_content = {}
            if self.env_file.exists():
                with open(self.env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            env_content[key.strip()] = value.strip()
            
            # Update with new values
            env_content['COGNITO_USER_POOL_ID'] = config['user_pool_id']
            env_content['COGNITO_APP_CLIENT_ID'] = config['client_id']
            if 'client_secret' in config:
                env_content['COGNITO_APP_CLIENT_SECRET'] = config['client_secret']
            env_content['COGNITO_DOMAIN'] = config['domain']
            env_content['COGNITO_RESOURCE_SERVER_ID'] = 'lakehouse-api'
            
            # Construct User Pool ARN
            account_id = boto3.client('sts').get_caller_identity()['Account']
            user_pool_arn = f"arn:aws:cognito-idp:{self.region}:{account_id}:userpool/{config['user_pool_id']}"
            env_content['COGNITO_USER_POOL_ARN'] = user_pool_arn
            
            # Write back to .env file
            with open(self.env_file, 'w') as f:
                for key, value in sorted(env_content.items()):
                    f.write(f"{key}={value}\n")
            
            print(f"\n✅ Configuration written to {self.env_file} (for backward compatibility)")
            
        except Exception as e:
            print(f"❌ Error writing to .env file: {e}")
            raise

    def setup(self, pool_name: str = 'lakehouse-pool') -> Dict:
        # Check for existing User Pool
        user_pool_id = self.find_existing_user_pool(pool_name)
        
        if not user_pool_id:
            # Create User Pool
            pool_response = self.cognito.create_user_pool(
                PoolName=pool_name,
                Policies={'PasswordPolicy': {'MinimumLength': 8, 'RequireUppercase': True, 'RequireLowercase': True, 'RequireNumbers': True}},
                AutoVerifiedAttributes=['email'],
                UsernameAttributes=['email'],
                Schema=[{'Name': 'email', 'Required': True}]
            )
            user_pool_id = pool_response['UserPool']['Id']
            print(f"✅ User Pool created: {user_pool_id}")
        else:
            print(f"✅ Using existing User Pool: {user_pool_id}")

        # Create Resource Server with scopes (if not exists)
        # Note: Scope names cannot contain '/' - using '.' instead
        try:
            resource_server = self.cognito.create_resource_server(
                UserPoolId=user_pool_id,
                Identifier='lakehouse-api',
                Name='Lakehouse Data API',
                Scopes=[
                    {'ScopeName': 'claims.query', 'ScopeDescription': 'Query claims'},
                    {'ScopeName': 'claims.submit', 'ScopeDescription': 'Submit claims'},
                    {'ScopeName': 'claims.update', 'ScopeDescription': 'Update claims'},
                    {'ScopeName': 'claims.approve', 'ScopeDescription': 'Approve/deny claims'}
                ]
            )
            print("✅ Resource Server created with scopes")
        except self.cognito.exceptions.ResourceNotFoundException:
            print("ℹ️  Resource Server already exists")
        except Exception as e:
            if 'already exists' in str(e).lower():
                print("ℹ️  Resource Server already exists")
            else:
                raise

        # Check for existing App Client
        existing_client = self.get_user_pool_client(user_pool_id, 'lakehouse-client')
        
        if existing_client:
            client_id = existing_client['ClientId']
            client_secret = existing_client.get('ClientSecret')
            print(f"ℹ️  App Client exists: {client_id}")
            print(f"   Updating to use client_credentials flow...")
            
            # Update existing client to use client_credentials flow
            self.cognito.update_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=client_id,
                ClientName='lakehouse-client',
                ExplicitAuthFlows=['ALLOW_USER_SRP_AUTH', 'ALLOW_REFRESH_TOKEN_AUTH'],
                AllowedOAuthFlows=['client_credentials'],  # Machine-to-machine authentication
                AllowedOAuthScopes=[
                    'lakehouse-api/claims.query',
                    'lakehouse-api/claims.submit',
                    'lakehouse-api/claims.update',
                    'lakehouse-api/claims.approve'
                ],
                AllowedOAuthFlowsUserPoolClient=True
            )
            print(f"✅ App Client updated to use client_credentials flow")
        else:
            # Create App Client for machine-to-machine authentication (client credentials flow)
            client_response = self.cognito.create_user_pool_client(
                UserPoolId=user_pool_id,
                ClientName='lakehouse-client',
                GenerateSecret=True,
                ExplicitAuthFlows=['ALLOW_USER_SRP_AUTH', 'ALLOW_REFRESH_TOKEN_AUTH'],
                AllowedOAuthFlows=['client_credentials'],  # Machine-to-machine authentication
                AllowedOAuthScopes=[
                    'lakehouse-api/claims.query',
                    'lakehouse-api/claims.submit',
                    'lakehouse-api/claims.update',
                    'lakehouse-api/claims.approve'
                ],
                AllowedOAuthFlowsUserPoolClient=True
            )
            client_id = client_response['UserPoolClient']['ClientId']
            client_secret = client_response['UserPoolClient'].get('ClientSecret')
            print(f"✅ App Client created: {client_id}")

        # Check for existing domain or create new one
        domain_url = self.get_user_pool_domain(user_pool_id)
        
        if not domain_url:
            # Create domain
            # Domain names can only contain lowercase letters, numbers, and hyphens
            # Extract only alphanumeric characters from pool ID and convert to lowercase
            pool_id_clean = re.sub(r'[^a-zA-Z0-9]', '', user_pool_id).lower()[:8]
            domain_name = f'lakehouse-{pool_id_clean}'
            
            try:
                self.cognito.create_user_pool_domain(Domain=domain_name, UserPoolId=user_pool_id)
                domain_url = f'https://{domain_name}.auth.{self.region}.amazoncognito.com'
                print(f"✅ Domain created: {domain_url}")
            except Exception as e:
                if 'already exists' in str(e).lower() or 'domain' in str(e).lower():
                    domain_url = f'https://{domain_name}.auth.{self.region}.amazoncognito.com'
                    print(f"ℹ️  Domain already exists: {domain_url}")
                else:
                    raise
        else:
            print(f"✅ Using existing domain: {domain_url}")

        # Create test users (skip if already exist)
        for email in ['user001@example.com', 'user002@example.com', 'adjuster001@example.com']:
            try:
                self.cognito.admin_create_user(
                    UserPoolId=user_pool_id,
                    Username=email,
                    UserAttributes=[{'Name': 'email', 'Value': email}, {'Name': 'email_verified', 'Value': 'true'}],
                    TemporaryPassword='TempPass123!',
                    MessageAction='SUPPRESS'
                )
                print(f"✅ Test user created: {email}")
            except self.cognito.exceptions.UsernameExistsException:
                print(f"ℹ️  Test user already exists: {email}")
            except Exception as e:
                if 'already exists' in str(e).lower():
                    print(f"ℹ️  Test user already exists: {email}")
                else:
                    print(f"⚠️  Error creating user {email}: {e}")

        result = {
            'user_pool_id': user_pool_id,
            'client_id': client_id,
            'domain': domain_url
        }
        
        if 'client_secret' in locals() and client_secret:
            result['client_secret'] = client_secret
        
        # Write to .env file (deprecated, for backward compatibility)
        self.write_to_env(result)
        
        return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', default='us-east-1')
    args = parser.parse_args()
    setup = CognitoSetup(args.region)
    result = setup.setup()
    print(f"\n📝 Configuration:\n{json.dumps(result, indent=2)}")
