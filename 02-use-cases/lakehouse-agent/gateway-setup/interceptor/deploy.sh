#!/bin/bash
# Deploy Gateway Interceptor Lambda Function

set -e

echo "🚀 Deploying Gateway Interceptor Lambda"

# Load environment variables from .env file
if [ -f "../../.env" ]; then
    echo "📄 Loading environment variables from .env"
    set -a
    source ../../.env
    set +a
else
    echo "⚠️  Warning: .env file not found, using defaults"
fi

# Check environment variables
if [ -z "$AWS_REGION" ]; then
    AWS_REGION="us-east-1"
fi

echo "   Region: $AWS_REGION"

# Package Lambda function
echo ""
echo "📦 Packaging Lambda function..."

mkdir -p dist
pip install -r requirements.txt -t dist/ --platform manylinux2014_x86_64 --only-binary=:all:
cp lambda_function.py dist/

cd dist
zip -r ../interceptor-lambda.zip .
cd ..

echo "✅ Package created: interceptor-lambda.zip"

# Create Lambda role using Python script
echo ""
echo "🔑 Creating Lambda execution role..."
cd ..
python create_lambda_role.py
cd interceptor

# Get the role ARN using AWS CLI
LAMBDA_ROLE_ARN=$(aws iam get-role --role-name InsuranceClaimsGatewayInterceptorRole --query 'Role.Arn' --output text 2>/dev/null)

if [ -z "$LAMBDA_ROLE_ARN" ]; then
    echo "❌ Failed to retrieve Lambda role ARN"
    exit 1
fi

echo "✅ Lambda role ready: $LAMBDA_ROLE_ARN"

# Check if Lambda function already exists
echo ""
echo "🔍 Checking if Lambda function exists..."
if aws lambda get-function --function-name lakehouse-gateway-interceptor --region $AWS_REGION 2>/dev/null; then
    echo "📝 Updating existing Lambda function..."
    aws lambda update-function-code \
        --function-name lakehouse-gateway-interceptor \
        --zip-file fileb://interceptor-lambda.zip \
        --region $AWS_REGION
    
    echo "⚙️  Updating Lambda configuration..."
    aws lambda update-function-configuration \
        --function-name lakehouse-gateway-interceptor \
        --environment "Variables={COGNITO_REGION=$AWS_REGION,COGNITO_USER_POOL_ID=$COGNITO_USER_POOL_ID,COGNITO_APP_CLIENT_ID=$COGNITO_APP_CLIENT_ID}" \
        --region $AWS_REGION
    
    echo "✅ Lambda function updated!"
else
    echo "📝 Creating new Lambda function..."
    aws lambda create-function \
        --function-name lakehouse-gateway-interceptor \
        --runtime python3.11 \
        --role $LAMBDA_ROLE_ARN \
        --handler lambda_function.lambda_handler \
        --zip-file fileb://interceptor-lambda.zip \
        --timeout 30 \
        --memory-size 256 \
        --environment "Variables={COGNITO_REGION=$AWS_REGION,COGNITO_USER_POOL_ID=$COGNITO_USER_POOL_ID,COGNITO_APP_CLIENT_ID=$COGNITO_APP_CLIENT_ID}" \
        --region $AWS_REGION
    
    echo "✅ Lambda function created!"
fi

echo ""
echo "✨ Deployment complete!"
echo ""
echo "📝 Lambda Function ARN:"
aws lambda get-function --function-name lakehouse-gateway-interceptor --region $AWS_REGION --query 'Configuration.FunctionArn' --output text
