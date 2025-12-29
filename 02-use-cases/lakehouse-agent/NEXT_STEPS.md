# Next Steps to Fix 424 Error

## Problem Summary

The agent runtime is returning a 424 (Failed Dependency) error. Investigation shows:

- ✅ Cognito token acquisition works perfectly
- ✅ Gateway is deployed and ready
- ✅ MCP server runtime is deployed
- ❌ Claims agent runtime has no logs (0 bytes in CloudWatch)
- ❌ Runtime container appears not to be starting

## Root Cause

The agent runtime container is not starting properly. This could be due to:
1. Docker build failure during deployment
2. Missing dependencies in the container
3. Runtime initialization error
4. Configuration issue

## Solution: Redeploy the Lakehouse Agent

### Step 1: Navigate to Lakehouse Agent Directory
```bash
cd 02-use-cases/lakehouse-processor/lakehouse-agent
```

### Step 2: Verify Prerequisites
```bash
# Ensure Docker is running
docker ps

# Ensure AWS credentials are configured
aws sts get-caller-identity

# Verify Gateway ARN is in .env
grep GATEWAY_ARN ../.env
```

### Step 3: Redeploy the Agent
```bash
python deploy_lakehouse_agent.py
```

**What this does:**
1. Creates/updates IAM execution role with required permissions
2. Builds a Docker container with your agent code
3. Pushes container to Amazon ECR
4. Creates a new AgentCore Runtime instance
5. Updates `.env` with new runtime ARN

**Expected output:**
```
============================================================
Lakehouse Data Agent Deployment to AgentCore Runtime
============================================================

🔍 Validating configuration...
✅ Configuration validated

📋 Configuration:
   Region: us-east-1
   Gateway ARN: arn:aws:bedrock-agentcore:us-east-1:XXXXXXXXXXXX:gateway/...

Proceed with deployment? (yes/no): yes

============================================================
Step 1: Creating IAM Role
============================================================
🔑 Creating IAM role: AgentCoreRuntimeRole-lakehouse-agent
✅ Created IAM role: arn:aws:iam::...

============================================================
Step 2: Deploying to AgentCore Runtime
============================================================
🚀 Deploying Lakehouse Agent to AgentCore Runtime...
   Name: lakehouse_agent
   Region: us-east-1
   This will build a Docker container and deploy it...

📋 Environment variables:
   GATEWAY_ARN: arn:aws:bedrock-agentcore:...
   AWS_REGION: us-east-1

🔧 Configuring AgentCore Runtime...
✅ Configuration complete

🚀 Launching to AgentCore Runtime...
   This may take several minutes...

✅ Lakehouse Agent deployed successfully!
   Runtime ARN: arn:aws:bedrock-agentcore:us-east-1:XXXXXXXXXXXX:runtime/lakehouse_agent-XXXXXXXX
   Runtime ID: lakehouse_agent-XXXXXXXX

============================================================
Deployment Complete!
============================================================
```

### Step 4: Wait for Runtime to Initialize
Wait 2-3 minutes for the runtime to fully initialize.

### Step 5: Test the Agent

#### Test 1: Simple Test (No Gateway)
```bash
cd ..
python test_agent_simple.py
```

Expected: Agent responds to "Hello, can you introduce yourself?"

#### Test 2: Full E2E Test (With Cognito Token)
```bash
python test_e2e_flow.py
```

Expected:
```
============================================================
🧪 Testing End-to-End Flow
============================================================
🔑 Getting Cognito bearer token...
✅ Token obtained: eyJraWQiOiJxxx...

🤖 Invoking agent runtime...
✅ Agent response:
{
  "content": "Here are your claims...",
  "tool_calls": 1
}

============================================================
✅ End-to-end test completed!
============================================================
```

### Step 6: Launch Streamlit UI
```bash
cd streamlit-ui
streamlit run streamlit_app.py
```

## Alternative: Check for Deployment Issues

If redeployment fails, check:

### 1. Docker Status
```bash
docker ps
docker images | grep insurance
```

### 2. ECR Repository
```bash
aws ecr describe-repositories --region us-east-1 | grep insurance
```

### 3. IAM Role Permissions
```bash
aws iam get-role --role-name AgentCoreRuntimeRole-lakehouse-agent
```

### 4. Bedrock Model Access
```bash
aws bedrock list-foundation-models --region us-east-1 | grep "claude-sonnet-4"
```

## Troubleshooting

### Issue: Docker not running
```bash
# macOS
open -a Docker

# Linux
sudo systemctl start docker
```

### Issue: AWS credentials expired
```bash
aws configure
# Or refresh your SSO session
aws sso login
```

### Issue: Insufficient permissions
Ensure your AWS user/role has:
- `BedrockAgentCoreFullAccess`
- `AmazonBedrockFullAccess`
- `IAMFullAccess` (for role creation)
- `AmazonEC2ContainerRegistryFullAccess` (for ECR)

## Success Criteria

After redeployment, you should see:
- ✅ New runtime ARN in `.env` file
- ✅ CloudWatch logs showing agent initialization
- ✅ `test_agent_simple.py` passes
- ✅ `test_e2e_flow.py` passes with Cognito token
- ✅ Streamlit UI can query claims

## Timeline

- Redeployment: 5-10 minutes
- Runtime initialization: 2-3 minutes
- Testing: 5 minutes
- **Total: ~15-20 minutes**

## Questions?

Refer to:
- `TROUBLESHOOTING.md` - Detailed troubleshooting guide
- `DEPLOYMENT_STATUS.md` - Current deployment status
- `README.md` - Complete setup instructions
