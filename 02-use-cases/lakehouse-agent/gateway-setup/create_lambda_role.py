#!/usr/bin/env python3
"""
Create IAM role for Gateway Interceptor Lambda
"""
import boto3
import json
import sys

def create_lambda_role():
    """Create IAM role for Lambda execution."""
    iam = boto3.client('iam')
    sts = boto3.client('sts')
    
    account_id = sts.get_caller_identity()['Account']
    role_name = 'InsuranceClaimsGatewayInterceptorRole'
    
    # Trust policy for Lambda
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    try:
        # Create role
        print(f"Creating IAM role: {role_name}")
        response = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description='Lambda execution role for Gateway Interceptor'
        )
        role_arn = response['Role']['Arn']
        print(f"✅ Created IAM role: {role_arn}")
        
        # Attach basic Lambda execution policy
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
        )
        print(f"✅ Attached AWSLambdaBasicExecutionRole policy")
        
        return role_arn
        
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"ℹ️  Role {role_name} already exists, retrieving ARN")
        response = iam.get_role(RoleName=role_name)
        role_arn = response['Role']['Arn']
        print(f"✅ Using existing role: {role_arn}")
        return role_arn
    except Exception as e:
        print(f"❌ Error creating role: {e}")
        sys.exit(1)

if __name__ == '__main__':
    role_arn = create_lambda_role()
    print(f"\n📝 Lambda Role ARN: {role_arn}")
    print(f"\nUse this ARN in your Lambda create-function command:")
    print(f"  --role {role_arn}")
