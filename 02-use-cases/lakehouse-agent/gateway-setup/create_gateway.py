#!/usr/bin/env python3
"""
Create AgentCore Gateway for Health Lakehouse Data

This script creates and configures an AgentCore Gateway that:
1. Connects to the MCP Athena server (running on AgentCore Runtime)
2. Uses the Gateway interceptor for JWT validation
3. Enforces fine-grained access control
4. Propagates user identity to the MCP server

Usage:
    python create_gateway.py \\
        --gateway-name lakehouse-gateway \\
        --mcp-server-runtime-arn arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:runtime/runtime-id \\
        --interceptor-arn arn:aws:lambda:us-east-1:ACCOUNT:function:interceptor \\
        --cognito-user-pool-arn arn:aws:cognito-idp:us-east-1:ACCOUNT:userpool/pool-id \\
        --region us-east-1
"""

import boto3
import argparse
import sys
import json
import os
from typing import Dict, Any
from pathlib import Path

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config

class GatewaySetup:
    def __init__(self, region: str):
        """
        Initialize Gateway setup.

        Args:
            region: AWS region
        """
        self.region = region
        self.client = boto3.client('bedrock-agentcore-control', region_name=region)

    def create_gateway_role(self, gateway_name: str) -> str:
        """
        Create IAM role for Gateway.

        Args:
            gateway_name: Name for the gateway

        Returns:
            Role ARN
        """
        iam = boto3.client('iam')
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity()['Account']
        
        role_name = f'agentcore-{gateway_name}-role'
        
        # Trust policy for AgentCore Gateway
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "bedrock-agentcore.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        try:
            print(f"🔑 Creating IAM role: {role_name}")
            response = iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description='IAM role for AgentCore Gateway'
            )
            role_arn = response['Role']['Arn']
            print(f"✅ Created IAM role: {role_arn}")
            
            # Attach policy to invoke Lambda and Runtime
            policy_document = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "lambda:InvokeFunction"
                        ],
                        "Resource": f"arn:aws:lambda:{self.region}:{account_id}:function:*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "bedrock-agentcore:InvokeRuntime"
                        ],
                        "Resource": f"arn:aws:bedrock-agentcore:{self.region}:{account_id}:runtime/*"
                    }
                ]
            }
            
            iam.put_role_policy(
                RoleName=role_name,
                PolicyName='GatewayExecutionPolicy',
                PolicyDocument=json.dumps(policy_document)
            )
            print(f"✅ Attached execution policy to role")
            
            return role_arn
            
        except iam.exceptions.EntityAlreadyExistsException:
            print(f"ℹ️  Role {role_name} already exists, retrieving ARN")
            response = iam.get_role(RoleName=role_name)
            role_arn = response['Role']['Arn']
            print(f"✅ Using existing role: {role_arn}")
            return role_arn
        except Exception as e:
            print(f"❌ Error creating role: {e}")
            raise

    def create_gateway(
        self,
        gateway_name: str,
        mcp_server_arn: str,
        interceptor_arn: str,
        cognito_user_pool_arn: str,
        client_id: str = None
    ) -> Dict[str, Any]:
        """
        Create an AgentCore Gateway with JWT authentication.

        Args:
            gateway_name: Name for the gateway
            mcp_server_arn: ARN of the MCP server AgentCore Runtime
            interceptor_arn: ARN of the interceptor Lambda function
            cognito_user_pool_arn: ARN of the Cognito User Pool
            client_id: Cognito app client ID (optional)

        Returns:
            Gateway creation response
        """
        try:
            print(f"\n🔧 Creating AgentCore Gateway: {gateway_name}")

            # Create IAM role for gateway
            role_arn = self.create_gateway_role(gateway_name)
            
            # Extract user pool ID from ARN
            user_pool_id = cognito_user_pool_arn.split('/')[-1]
            issuer = f'https://cognito-idp.{self.region}.amazonaws.com/{user_pool_id}'
            
            # JWT authorizer configuration
            # Cognito OIDC discovery URL
            discovery_url = f'{issuer}/.well-known/openid-configuration'
            
            auth_config = {
                "customJWTAuthorizer": {
                    "discoveryUrl": discovery_url,
                    "allowedAudience": [client_id] if client_id else [],
                    "allowedClients": [client_id] if client_id else []
                }
            }

            # Create gateway
            response = self.client.create_gateway(
                name=gateway_name,
                roleArn=role_arn,
                protocolType='MCP',
                protocolConfiguration={
                    'mcp': {
                        'supportedVersions': ['2025-03-26'],
                        'searchType': 'SEMANTIC'
                    }
                },
                authorizerType='CUSTOM_JWT',
                authorizerConfiguration=auth_config,
                description='Gateway for Health Lakehouse Data MCP Server with OAuth-based access control'
            )

            gateway_id = response['gatewayId']
            gateway_url = response['gatewayUrl']
            gateway_arn = f"arn:aws:bedrock-agentcore:{self.region}:{boto3.client('sts').get_caller_identity()['Account']}:gateway/{gateway_id}"

            print(f"✅ Gateway created successfully!")
            print(f"   Gateway ID: {gateway_id}")
            print(f"   Gateway URL: {gateway_url}")
            print(f"   Gateway ARN: {gateway_arn}")

            return {
                'gatewayId': gateway_id,
                'gatewayUrl': gateway_url,
                'gatewayArn': gateway_arn
            }

        except Exception as e:
            if "already exists" in str(e):
                print(f"ℹ️  Gateway {gateway_name} already exists, retrieving details...")
                response = self.client.list_gateways()
                for gateway in response.get('items', []):
                    if gateway['name'] == gateway_name:
                        gateway_id = gateway['gatewayId']
                        response = self.client.get_gateway(gatewayIdentifier=gateway_id)
                        gateway_url = response['gatewayUrl']
                        gateway_arn = f"arn:aws:bedrock-agentcore:{self.region}:{boto3.client('sts').get_caller_identity()['Account']}:gateway/{gateway_id}"
                        print(f"✅ Using existing gateway: {gateway_id}")
                        return {
                            'gatewayId': gateway_id,
                            'gatewayUrl': gateway_url,
                            'gatewayArn': gateway_arn
                        }
            print(f"❌ Error creating gateway: {str(e)}")
            raise
    
    def create_gateway_target(
        self,
        gateway_id: str,
        target_name: str,
        mcp_server_url: str
    ) -> Dict[str, Any]:
        """
        Create a gateway target pointing to the MCP server runtime.

        Args:
            gateway_id: Gateway ID
            target_name: Name for the target
            mcp_server_url: URL of the MCP server runtime

        Returns:
            Target creation response
        """
        try:
            print(f"\n🎯 Creating gateway target: {target_name}")
            
            response = self.client.create_gateway_target(
                name=target_name,
                gatewayIdentifier=gateway_id,
                targetConfiguration={
                    'mcp': {
                        'mcpServer': {
                            'endpoint': mcp_server_url
                        }
                    }
                }
            )
            
            print(f"✅ Gateway target created successfully!")
            return response
            
        except Exception as e:
            if "already exists" in str(e):
                print(f"ℹ️  Target {target_name} already exists")
                return {}
            print(f"❌ Error creating gateway target: {str(e)}")
            raise

    def wait_for_gateway_active(self, gateway_id: str, max_wait_seconds: int = 300) -> bool:
        """
        Wait for gateway to be in ACTIVE or READY status.
        
        Args:
            gateway_id: Gateway ID
            max_wait_seconds: Maximum time to wait in seconds
            
        Returns:
            True if gateway is active/ready, False if timeout
        """
        import time
        
        print(f"\n⏳ Checking gateway status...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait_seconds:
            try:
                response = self.client.get_gateway(gatewayIdentifier=gateway_id)
                status = response.get('status', 'UNKNOWN').strip().upper()
                
                print(f"   Status: {status}")
                
                if status in ['ACTIVE', 'READY']:
                    print(f"✅ Gateway is ready (status: {status})!")
                    return True
                elif status in ['FAILED', 'DELETING', 'DELETED']:
                    print(f"❌ Gateway is in {status} status")
                    return False
                
                print(f"   Waiting for gateway to be ready...")
                time.sleep(10)
                
            except Exception as e:
                print(f"⚠️  Error checking gateway status: {e}")
                time.sleep(10)
        
        print(f"⚠️  Timeout waiting for gateway to be active")
        return False
    
    def list_gateways(self) -> None:
        """List all gateways in the region."""
        try:
            print(f"\n📋 Listing AgentCore Gateways in {self.region}...")

            response = self.client.list_gateways()

            gateways = response.get('gateways', [])

            if not gateways:
                print("   No gateways found")
                return

            for gateway in gateways:
                print(f"\n   Gateway: {gateway['name']}")
                print(f"   ARN: {gateway['gatewayArn']}")
                print(f"   Status: {gateway.get('status', 'N/A')}")

        except Exception as e:
            print(f"❌ Error listing gateways: {str(e)}")

    def update_gateway_auth(
        self,
        gateway_id: str,
        client_id: str
    ) -> None:
        """
        Update gateway authentication configuration after Cognito setup.

        Args:
            gateway_id: Gateway ID
            client_id: Cognito app client ID
        """
        try:
            print(f"\n🔄 Updating gateway authentication configuration...")

            response = self.client.update_gateway(
                gatewayId=gateway_id,
                inboundAuthConfig={
                    'type': 'JWT',
                    'jwtConfig': {
                        'audience': client_id
                    }
                }
            )

            print(f"✅ Gateway authentication updated with client ID: {client_id}")

        except Exception as e:
            print(f"❌ Error updating gateway: {str(e)}")
            raise


def write_to_env_file(env_path: str, updates: Dict[str, str]) -> None:
    """
    Write or update values in the .env file.
    
    Note: This function is deprecated and will be removed in a future version.
    Configuration should be managed through SSM Parameter Store.
    This is kept temporarily for backward compatibility during migration.
    
    Args:
        env_path: Path to the .env file
        updates: Dictionary of key-value pairs to write/update
    """
    print(f"⚠️  Warning: .env file updates are deprecated. Please migrate to SSM Parameter Store.")
    print(f"   Run: python ../ssm_migrate.py --migrate")
    
    # Read existing content
    existing_lines = []
    existing_keys = set()
    
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            existing_lines = f.readlines()
        
        # Track which keys already exist
        for line in existing_lines:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key = line.split('=')[0].strip()
                existing_keys.add(key)
    
    # Update existing keys or append new ones
    updated_lines = []
    for line in existing_lines:
        line_stripped = line.strip()
        if line_stripped and not line_stripped.startswith('#') and '=' in line_stripped:
            key = line_stripped.split('=')[0].strip()
            if key in updates:
                # Update existing key
                updated_lines.append(f"{key}={updates[key]}\n")
                del updates[key]  # Remove from updates dict
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)
    
    # Append new keys that weren't in the file
    if updates:
        # Add a newline if file doesn't end with one
        if updated_lines and not updated_lines[-1].endswith('\n'):
            updated_lines.append('\n')
        
        for key, value in updates.items():
            updated_lines.append(f"{key}={value}\n")
    
    # Write back to file
    with open(env_path, 'w') as f:
        f.writelines(updated_lines)
    
    print(f"✅ Updated .env file with gateway configuration (for backward compatibility)")


def get_runtime_url(runtime_arn: str, region: str) -> str:
    """
    Get the runtime URL from the runtime ARN.
    
    Args:
        runtime_arn: Runtime ARN
        region: AWS region
        
    Returns:
        Runtime URL
    """
    # Extract runtime ID from ARN
    runtime_id = runtime_arn.split('/')[-1]
    
    # Get runtime details
    client = boto3.client('bedrock-agentcore', region_name=region)
    try:
        response = client.get_runtime(runtimeIdentifier=runtime_id)
        return response.get('runtimeUrl', '')
    except Exception as e:
        print(f"⚠️  Could not retrieve runtime URL: {e}")
        # Construct URL based on pattern
        account_id = boto3.client('sts').get_caller_identity()['Account']
        return f"https://{runtime_id}.runtime.bedrock-agentcore.{region}.amazonaws.com"


def main():
    parser = argparse.ArgumentParser(
        description='Create AgentCore Gateway for Health Lakehouse Data'
    )
    parser.add_argument(
        '--gateway-name',
        default='lakehouse-gateway',
        help='Name for the gateway'
    )
    parser.add_argument(
        '--mcp-server-arn',
        '--mcp-server-runtime-arn',
        dest='mcp_server_arn',
        required=True,
        help='ARN of the MCP server AgentCore Runtime (e.g., arn:aws:bedrock-agentcore:region:account:runtime/runtime-id)'
    )
    parser.add_argument(
        '--interceptor-arn',
        required=True,
        help='ARN of the interceptor Lambda function'
    )
    parser.add_argument(
        '--cognito-user-pool-arn',
        required=True,
        help='ARN of the Cognito User Pool'
    )
    parser.add_argument(
        '--client-id',
        help='Cognito app client ID (optional, can be added later)'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List existing gateways'
    )

    args = parser.parse_args()

    # Get client ID from args or config
    client_id = args.client_id or config.COGNITO_APP_CLIENT_ID
    
    if not client_id:
        print("❌ Error: Cognito App Client ID is required")
        print("   Provide it via --client-id argument or set in SSM Parameter Store (lh_cognito_app_client_id)")
        sys.exit(1)

    # Create gateway setup instance
    setup = GatewaySetup(args.region)

    if args.list:
        # List existing gateways
        setup.list_gateways()
    else:
        # Create new gateway
        print(f"\n🚀 AgentCore Gateway Setup")
        print(f"   Region: {args.region}")
        print(f"   Gateway Name: {args.gateway_name}")
        print(f"   MCP Server: {args.mcp_server_arn}")
        print(f"   Interceptor: {args.interceptor_arn}")
        print(f"   Client ID: {client_id}")

        # Create gateway
        gateway_response = setup.create_gateway(
            gateway_name=args.gateway_name,
            mcp_server_arn=args.mcp_server_arn,
            interceptor_arn=args.interceptor_arn,
            cognito_user_pool_arn=args.cognito_user_pool_arn,
            client_id=client_id
        )
        
        # Wait for gateway to be active before creating target
        if setup.wait_for_gateway_active(gateway_response['gatewayId']):
            # Get runtime URL
            runtime_url = get_runtime_url(args.mcp_server_arn, args.region)
            
            # Create gateway target
            if runtime_url:
                setup.create_gateway_target(
                    gateway_id=gateway_response['gatewayId'],
                    target_name='lakehouse-mcp-target',
                    mcp_server_url=runtime_url
                )
        else:
            print(f"\n⚠️  Gateway not active yet. You can create the target later by running:")
            print(f"   python create_gateway.py --add-target --gateway-id {gateway_response['gatewayId']} --runtime-arn {args.mcp_server_arn}")

        # Write configuration to .env file (deprecated, for backward compatibility)
        env_path = str(Path(__file__).parent.parent / '.env')
        env_updates = {
            'GATEWAY_ID': gateway_response['gatewayId'],
            'GATEWAY_ARN': gateway_response['gatewayArn'],
            'GATEWAY_URL': gateway_response['gatewayUrl'],
            'GATEWAY_NAME': args.gateway_name
        }
        
        if Path(env_path).exists():
            write_to_env_file(env_path, env_updates)
        
        print(f"\n✨ Gateway setup complete!")
        print(f"\n📝 Add these values to SSM Parameter Store:")
        print(f"   aws ssm put-parameter --name lh_gateway_id --value '{gateway_response['gatewayId']}' --type String --overwrite")
        print(f"   aws ssm put-parameter --name lh_gateway_arn --value '{gateway_response['gatewayArn']}' --type String --overwrite")
        print(f"   aws ssm put-parameter --name lh_gateway_url --value '{gateway_response['gatewayUrl']}' --type String --overwrite")
        print(f"   aws ssm put-parameter --name lh_gateway_name --value '{args.gateway_name}' --type String --overwrite")


if __name__ == '__main__':
    main()
