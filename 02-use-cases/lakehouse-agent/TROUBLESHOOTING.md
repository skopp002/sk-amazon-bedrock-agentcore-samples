# Troubleshooting Guide

## Current Issue: 424 Error When Invoking Agent Runtime

### Symptoms
- Cognito token acquisition: ✅ Working
- Agent runtime invocation: ❌ 424 Error (Failed Dependency)

### Error Details
```
botocore.exceptions.ClientError: An error occurred (424) when calling the InvokeAgentRuntime operation:
```

### Possible Causes

1. **Runtime Not Fully Deployed**
   - The Docker container may not have built successfully
   - The runtime may still be initializing
   - Check CloudWatch logs for the runtime

2. **Missing Dependencies in Runtime**
   - The `strands` library may not be installed correctly
   - The `bedrock_agentcore` library may be missing
   - Check `requirements.txt` in lakehouse-agent directory

3. **Environment Variables Not Set**
   - `GATEWAY_ARN` may not be available to the runtime
   - Runtime may need to be redeployed with correct env vars

4. **IAM Permissions Issue**
   - Runtime execution role may lack required permissions
   - Check Bedrock model access permissions

### Diagnostic Steps

#### Step 1: Check CloudWatch Logs
```bash
# Get log group name (usually /aws/bedrock-agentcore/runtime/RUNTIME_ID)
aws logs describe-log-groups --region us-east-1 | grep lakehouse_agent

# View recent logs
aws logs tail /aws/bedrock-agentcore/runtime/lakehouse_agent-Hhb3lX6y7M --follow --region us-east-1
```

#### Step 2: Verify Requirements File
Check `lakehouse-agent/requirements.txt` includes:
```
strands-agents>=1.0.0
bedrock-agentcore>=1.0.0
python-dotenv>=1.0.0
```

#### Step 3: Redeploy the Agent
```bash
cd lakehouse-agent
python deploy_lakehouse_agent.py
```

This will:
- Rebuild the Docker container
- Redeploy to AgentCore Runtime
- Update environment variables

#### Step 4: Test Without Gateway
```bash
python test_agent_simple.py
```

This tests if the agent can respond to basic prompts without needing Gateway tools.

### Solution Options

#### Option A: Redeploy Agent (Recommended)
The most reliable fix is to redeploy the agent:

```bash
cd 02-use-cases/lakehouse-processor/lakehouse-agent
python deploy_lakehouse_agent.py
```

#### Option B: Check Runtime Status
Wait 5-10 minutes for the runtime to fully initialize, then retry.

#### Option C: Verify Bedrock Model Access
Ensure your AWS account has access to Claude Sonnet 4.5:
```bash
aws bedrock list-foundation-models --region us-east-1 | grep claude-sonnet-4
```

### Next Steps After Fix

Once the 424 error is resolved:

1. Run simple test:
   ```bash
   python test_agent_simple.py
   ```

2. Run full E2E test:
   ```bash
   python test_e2e_flow.py
   ```

3. Launch Streamlit UI:
   ```bash
   cd streamlit-ui
   streamlit run streamlit_app.py
   ```

### Common 424 Error Causes

| Cause | Solution |
|-------|----------|
| Runtime still initializing | Wait 5-10 minutes |
| Missing dependencies | Check requirements.txt |
| IAM permissions | Verify execution role |
| Model not available | Check Bedrock model access |
| Docker build failed | Check deployment logs |
| Environment vars missing | Redeploy with correct config |

### Getting Help

If the issue persists:

1. Check CloudWatch Logs for detailed error messages
2. Verify all prerequisites are met (Docker, AWS credentials, etc.)
3. Try deploying to a different region
4. Contact AWS Support with the runtime ARN and error details
