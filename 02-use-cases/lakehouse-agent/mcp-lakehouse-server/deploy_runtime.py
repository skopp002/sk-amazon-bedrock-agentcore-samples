#!/usr/bin/env python3
"""
Deploy MCP Athena Server to AgentCore Runtime

This script deploys the MCP server to Amazon Bedrock AgentCore Runtime using
the Bedrock AgentCore Starter Toolkit. The server provides secure Athena query
tools with Lake Formation RLS.

Prerequisites:
- AWS credentials configured
- Docker running
- Lake Formation RLS configured (run setup_lake_formation.py)
- Configuration in .env file
- bedrock-agentcore-starter-toolkit installed

Usage:
    python deploy_runtime.py
"""

import sys
from pathlib import Path

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
import json
from config import config

try:
    from bedrock_agentcore_starter_toolkit import Runtime
except ImportError:
    print("\n❌ Error: bedrock-agentcore-starter-toolkit not installed")
    print("   Please install it with: pip install bedrock-agentcore-starter-toolkit")
    sys.exit(1)

def create_runtime_role():
    """Create IAM role for AgentCore Runtime execution."""
    iam = boto3.client('iam', region_name=config.AWS_REGION)
    
    role_name = 'AgentCoreRuntimeRole-lakehouse-mcp'
    
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
                    "athena:StartQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:StopQueryExecution",
                    "athena:GetWorkGroup"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "glue:GetDatabase",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetPartition",
                    "glue:GetPartitions"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:PutObject"
                ],
                "Resource": [
                    f"arn:aws:s3:::{config.S3_BUCKET_NAME}/*",
                    f"arn:aws:s3:::{config.S3_BUCKET_NAME}"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "sts:AssumeRole"
                ],
                "Resource": config.RLS_ROLE_ARN
            },
            {
                "Effect": "Allow",
                "Action": [
                    "lakeformation:GetDataAccess"
                ],
                "Resource": "*"
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
            Description='AgentCore Runtime execution role for lakehouse data MCP server'
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
    """Deploy MCP server to AgentCore Runtime using starter toolkit."""
    runtime_name = 'lakehouse_mcp_server'  # Must use underscores, not hyphens
    
    try:
        print(f"\n🚀 Deploying MCP server to AgentCore Runtime...")
        print(f"   Name: {runtime_name}")
        print(f"   Region: {config.AWS_REGION}")
        print(f"   This will build a Docker container and deploy it...")
        
        # Build environment variables
        env_vars = {
            'AWS_REGION': config.AWS_REGION,
            'S3_BUCKET_NAME': config.S3_BUCKET_NAME,
            'ATHENA_DATABASE_NAME': config.ATHENA_DATABASE_NAME,
            'RLS_ROLE_ARN': config.RLS_ROLE_ARN,
            'SECURITY_MODE': 'lakeformation',
            'LOG_LEVEL': config.LOG_LEVEL
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
        
        # Note: Environment variables are read from config.py/.env file by the MCP server
        # The starter toolkit will package the entire directory including config files
        agentcore_runtime.configure(
            entrypoint="server.py",
            execution_role=role_name,  # Use role name, not ARN
            auto_create_ecr=True,
            requirements_file="requirements.txt",
            region=config.AWS_REGION,
            protocol="MCP",
            agent_name=runtime_name
        )
        print(f"✅ Configuration complete")
        
        # Launch the runtime (builds Docker image and deploys)
        print(f"\n🚀 Launching to AgentCore Runtime...")
        print(f"   This may take several minutes...")
        launch_result = agentcore_runtime.launch()
        
        runtime_arn = launch_result.agent_arn
        runtime_id = launch_result.agent_id
        
        print(f"\n✅ MCP Server deployed successfully!")
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


def main():
    """Main deployment function."""
    print("=" * 70)
    print("MCP Athena Server Deployment to AgentCore Runtime")
    print("=" * 70)
    
    # Validate configuration
    print("\n🔍 Validating configuration...")
    
    if not config.is_valid():
        print("\n❌ Configuration is invalid!")
        config.print_status()
        print("\n📝 Please update your .env file.")
        sys.exit(1)
    
    if not config.RLS_ROLE_ARN:
        print("\n❌ Error: Lake Formation RLS is not configured!")
        print("\n📝 Setup Lake Formation:")
        print("   cd athena-setup")
        print("   python setup_lake_formation.py")
        sys.exit(1)
    
    print("✅ Configuration validated")
    
    # Print configuration summary
    print(f"\n📋 Configuration:")
    print(f"   AWS Account: {config.AWS_ACCOUNT_ID}")
    print(f"   Region: {config.AWS_REGION}")
    print(f"   Database: {config.ATHENA_DATABASE_NAME}")
    print(f"   S3 Bucket: {config.S3_BUCKET_NAME}")
    print(f"   RLS Role: {config.RLS_ROLE_ARN}")
    print(f"   Security Mode: {config.SECURITY_MODE}")
    
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
        role_arn = create_runtime_role()
        
        # Step 2: Deploy to runtime
        print("\n" + "=" * 70)
        print("Step 2: Deploying to AgentCore Runtime")
        print("=" * 70)
        result = deploy_to_runtime(role_arn)
        
        # Print summary
        print("\n" + "=" * 70)
        print("Deployment Complete!")
        print("=" * 70)
        
        print("\n📝 Add these values to your .env file:\n")
        print(f"MCP_SERVER_RUNTIME_ARN={result['runtime_arn']}")
        print(f"MCP_SERVER_RUNTIME_ID={result['runtime_id']}")
        
        print("\n🔗 Next Steps:")
        print("   1. Update your .env file with the values above")
        print("   2. Deploy the Gateway and Interceptor (Step 7)")
        print("   3. Deploy the Lakehouse Agent (Step 8)")
        print("   4. Test the system end-to-end")
        
        print("\n" + "=" * 70)
        
    except Exception as e:
        print(f"\n❌ Deployment failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
