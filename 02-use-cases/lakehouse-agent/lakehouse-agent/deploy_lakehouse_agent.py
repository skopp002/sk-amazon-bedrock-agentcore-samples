#!/usr/bin/env python3
"""
Deploy Lakehouse Agent to AgentCore Runtime

This script deploys the health lakehouse data agent to Amazon Bedrock AgentCore Runtime
using the Bedrock AgentCore Starter Toolkit.

Prerequisites:
- AWS credentials configured
- Docker running
- Gateway configured (run create_gateway.py)
- Configuration in .env file
- bedrock-agentcore-starter-toolkit installed

Usage:
    python deploy_lakehouse_agent.py
"""

import sys
from pathlib import Path
import boto3
import json
import os
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"📄 Loaded environment variables from .env")

# Configuration
REGION = os.getenv('AWS_REGION', 'us-east-1')
GATEWAY_ARN = os.getenv('GATEWAY_ARN', '')
COGNITO_USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
COGNITO_APP_CLIENT_ID = os.getenv('COGNITO_APP_CLIENT_ID')

try:
    from bedrock_agentcore_starter_toolkit import Runtime
except ImportError:
    print("\n❌ Error: bedrock-agentcore-starter-toolkit not installed")
    print("   Please install it with: pip install bedrock-agentcore-starter-toolkit")
    sys.exit(1)


def create_agent_role():
    """Create IAM role for Lakehouse Agent Runtime execution."""
    iam = boto3.client('iam', region_name=REGION)
    sts = boto3.client('sts', region_name=REGION)
    account_id = sts.get_caller_identity()['Account']
    
    role_name = 'AgentCoreRuntimeRole-lakehouse-agent'
    
    # Trust policy for AgentCore Runtime
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
    
    # Permissions policy
    permissions_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:InvokeGateway",
                    "bedrock-agentcore:GetGateway"
                ],
                "Resource": f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:gateway/*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": "arn:aws:logs:*:*:*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage"
                ],
                "Resource": "*"
            }
        ]
    }
    
    try:
        # Create role
        print(f"Creating IAM role: {role_name}")
        response = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description='AgentCore Runtime execution role for lakehouse data agent'
        )
        role_arn = response['Role']['Arn']
        
        # Attach inline policy
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName='AgentCoreRuntimePermissions',
            PolicyDocument=json.dumps(permissions_policy)
        )
        
        print(f"✅ Created IAM role: {role_arn}")
        return role_arn
        
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"ℹ️  Role {role_name} already exists, retrieving ARN")
        response = iam.get_role(RoleName=role_name)
        role_arn = response['Role']['Arn']
        
        # Update the role policy to ensure it has all required permissions
        print(f"   Updating role policy with latest permissions...")
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName='AgentCoreRuntimePermissions',
            PolicyDocument=json.dumps(permissions_policy)
        )
        print(f"   ✅ Role policy updated")
        
        return role_arn


def deploy_to_runtime(role_arn):
    """Deploy lakehouse agent to AgentCore Runtime using starter toolkit."""
    runtime_name = 'lakehouse_agent'  # Must use underscores, not hyphens
    
    try:
        print(f"\n🚀 Deploying Lakehouse Agent to AgentCore Runtime...")
        print(f"   Name: {runtime_name}")
        print(f"   Region: {REGION}")
        print(f"   This will build a Docker container and deploy it...")
        
        # Build environment variables
        env_vars = {
            'GATEWAY_ARN': GATEWAY_ARN,
            'AWS_REGION': REGION
        }
        
        print(f"\n📋 Environment variables:")
        for key, value in env_vars.items():
            print(f"   {key}: {value}")
        
        # Initialize Runtime from starter toolkit
        agentcore_runtime = Runtime()
        
        # Configure the runtime
        print(f"\n🔧 Configuring AgentCore Runtime...")
        
        # Extract role name from ARN (format: arn:aws:iam::account:role/RoleName)
        role_name = role_arn.split('/')[-1]
        
        # Build configuration parameters
        config_params = {
            'entrypoint': "lakehouse_agent.py",
            'execution_role': role_name,  # Use role name, not ARN
            'auto_create_ecr': True,
            'requirements_file': "requirements.txt",
            'region': REGION,
            # Note: Not specifying protocol - will use default HTTP protocol for JWT auth
            'agent_name': runtime_name
        }
        
        # Add JWT authentication configuration if Cognito is configured
        if COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID:
            print(f"   Configuring JWT authentication...")
            issuer = f'https://cognito-idp.{REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}'
            discovery_url = f'{issuer}/.well-known/openid-configuration'
            
            print(f"   Discovery URL: {discovery_url}")
            print(f"   Allowed Clients: {COGNITO_APP_CLIENT_ID}")
            
            config_params['authorizer_configuration'] = {
                'customJWTAuthorizer': {
                    'allowedClients': [COGNITO_APP_CLIENT_ID],
                    'discoveryUrl': discovery_url
                }
            }
            
            # Add Authorization header to allowlist for OAuth token propagation
            config_params['request_header_configuration'] = {
                'requestHeaderAllowlist': ['Authorization']
            }
            
            print(f"✅ JWT authentication will be configured")
        else:
            print(f"⚠️  Cognito not configured - runtime will use IAM authentication")
        
        agentcore_runtime.configure(**config_params)
        print(f"✅ Configuration complete")
        
        # Launch the runtime (builds Docker image and deploys)
        print(f"\n🚀 Launching to AgentCore Runtime...")
        print(f"   This may take several minutes...")
        launch_result = agentcore_runtime.launch()
        
        runtime_arn = launch_result.agent_arn
        runtime_id = launch_result.agent_id
        
        print(f"\n✅ Lakehouse Agent deployed successfully!")
        print(f"   Runtime ARN: {runtime_arn}")
        print(f"   Runtime ID: {runtime_id}")
        
        return {
            'runtime_arn': runtime_arn,
            'runtime_id': runtime_id,
            'role_arn': role_arn
        }
        
    except Exception as e:
        print(f"\n❌ Error deploying runtime: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


def write_to_env_file(env_path, updates):
    """Write or update values in the .env file."""
    # Read existing content
    existing_lines = []
    existing_keys = set()
    
    if env_path.exists():
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
    
    print(f"✅ Updated .env file with agent configuration")


def main():
    """Main deployment function."""
    print("=" * 70)
    print("Lakehouse Data Agent Deployment to AgentCore Runtime")
    print("=" * 70)
    
    # Validate configuration
    print("\n🔍 Validating configuration...")
    
    if not GATEWAY_ARN:
        print("\n⚠️  Warning: GATEWAY_ARN not set in .env file")
        print("   The agent will not be able to access Gateway tools")
        response = input("\nProceed anyway? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Deployment cancelled")
            sys.exit(0)
    
    print("✅ Configuration validated")
    
    # Print configuration summary
    print(f"\n📋 Configuration:")
    print(f"   Region: {REGION}")
    print(f"   Gateway ARN: {GATEWAY_ARN or 'Not configured'}")
    
    # Confirm deployment
    response = input("\nProceed with deployment? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Deployment cancelled")
        sys.exit(0)
    
    try:
        # Step 1: Create IAM role
        print("\n" + "=" * 70)
        print("Step 1: Creating IAM Role")
        print("=" * 70)
        role_arn = create_agent_role()
        
        # Step 2: Deploy to runtime
        print("\n" + "=" * 70)
        print("Step 2: Deploying to AgentCore Runtime")
        print("=" * 70)
        result = deploy_to_runtime(role_arn)
        
        # Step 3: Write to .env file
        env_updates = {
            'LAKEHOUSE_AGENT_RUNTIME_ARN': result['runtime_arn'],
            'LAKEHOUSE_AGENT_RUNTIME_ID': result['runtime_id'],
            'LAKEHOUSE_AGENT_NAME': 'lakehouse_agent'
        }
        write_to_env_file(env_path, env_updates)
        
        # Print summary
        print("\n" + "=" * 70)
        print("Deployment Complete!")
        print("=" * 70)
        
        print("\n📝 Configuration saved to .env file:")
        print(f"   LAKEHOUSE_AGENT_RUNTIME_ARN={result['runtime_arn']}")
        print(f"   LAKEHOUSE_AGENT_RUNTIME_ID={result['runtime_id']}")
        print(f"   LAKEHOUSE_AGENT_NAME=lakehouse_agent")
        
        # Print JWT configuration status
        if COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID:
            print("\n✅ JWT Authentication Configured:")
            print(f"   Discovery URL: https://cognito-idp.{REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/openid-configuration")
            print(f"   Allowed Clients: {COGNITO_APP_CLIENT_ID}")
            print(f"   Authorization header: Enabled for OAuth token propagation")
        else:
            print("\n⚠️  JWT Authentication Not Configured:")
            print("   Runtime deployed with IAM authentication")
            print("   To enable JWT auth, set COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID in .env and redeploy")
        
        print("\n🔗 Next Steps:")
        print("   1. Test the agent: python ../test_agent_simple.py")
        print("   2. Test E2E flow: python ../test_e2e_flow.py")
        print("   3. Deploy the Streamlit UI: cd ../streamlit-ui && streamlit run streamlit_app.py")
        
        print("\n" + "=" * 70)
        
    except Exception as e:
        print(f"\n❌ Deployment failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
