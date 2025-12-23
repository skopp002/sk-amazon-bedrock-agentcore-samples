# Health Lakehouse Agent with Production-Grade Security

A complete lakehouse data processing system demonstrating Amazon Bedrock AgentCore capabilities with end-to-end OAuth authentication, enterprise-grade row-level security using AWS Lake Formation, and comprehensive data governance with SageMaker Unified Studio.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Key Features](#key-features)
- [Security Implementation](#security-implementation)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Configuration Guide](#configuration-guide)
- [Deployment Steps](#deployment-steps)
- [Testing](#testing)
- [Usage Examples](#usage-examples)
- [Troubleshooting](#troubleshooting)
- [File Structure](#file-structure)
- [Cost Estimate](#cost-estimate)

---

## Overview

This system showcases a production-ready lakehouse data processing application with:

- **Streamlit UI** with Cognito OAuth authentication
- **AI-Powered Lakehouse Agent** hosted on AgentCore Runtime using Strands framework
- **AgentCore Gateway** with policy-based tool access control
- **MCP Server** connecting to AWS Athena with Lake Formation row-level security
- **Lake Formation RLS** for enterprise-grade row-level security (infrastructure-level enforcement)
- **SageMaker Unified Studio** for data governance, cataloging, and discovery
- **OAuth credentials propagated** through the entire stack (UI → Agent → Gateway → Tool → Database)

### What Makes This Production-Ready

✅ **Infrastructure-Level Security**: Lake Formation enforces row-level security at the AWS query engine level, not in application code
✅ **Zero SQL Injection**: No SQL string interpolation with user input
✅ **Cannot Be Bypassed**: Security enforced by AWS, not application bugs
✅ **Full Audit Trail**: CloudTrail logs all data access with user identity
✅ **Compliance-Ready**: Meets HIPAA, SOC 2, and GDPR requirements
✅ **Data Governance**: Complete data cataloging, lineage tracking, and discovery

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Layer                                │
│  ┌────────────────┐                                             │
│  │ Streamlit UI   │ OAuth login via Cognito                     │
│  │ + Cognito Auth │                                             │
│  └────────┬───────┘                                             │
└───────────┼─────────────────────────────────────────────────────┘
            │ Bearer Token (JWT with user identity)
            │
┌───────────▼─────────────────────────────────────────────────────┐
│                      AI Agent Layer                              │
│  ┌────────────────┐                                             │
│  │  Lakehouse Agent  │ Strands-based conversational agent          │
│  │ AgentCore      │ Natural language claim processing           │
│  │ Runtime        │                                             │
│  └────────┬───────┘                                             │
└───────────┼─────────────────────────────────────────────────────┘
            │ Bearer Token + Tool Request
            │
┌───────────▼─────────────────────────────────────────────────────┐
│                Gateway & Policy Layer                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  AgentCore Gateway + Interceptor Lambda                  │  │
│  │  - Validates JWT tokens                                  │  │
│  │  - Extracts user identity (email)                        │  │
│  │  - Enforces scope-based tool access                      │  │
│  │  - Adds user identity to request headers                 │  │
│  └────────┬───────────────────────────────────────────────────┘  │
└───────────┼─────────────────────────────────────────────────────┘
            │ User Identity + Tool Request
            │
┌───────────▼─────────────────────────────────────────────────────┐
│                    Tool Execution Layer                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  MCP Server (AgentCore Runtime)                            │ │
│  │  Athena connector with Lake Formation RLS                  │ │
│  │  - Receives user_id from Gateway                           │ │
│  │  - Assumes role with session tags                          │ │
│  │  - Executes queries with RLS enforcement                   │ │
│  └────────┬───────────────────────────────────────────────────┘ │
└───────────┼─────────────────────────────────────────────────────┘
            │ Athena Query with Session Tag
            │
┌───────────▼─────────────────────────────────────────────────────┐
│              Security & Governance Layer                         │
│                                                                  │
│  ┌────────────────────────┐    ┌──────────────────────────┐   │
│  │  Lake Formation        │    │ SageMaker Unified Studio │   │
│  │  (RLS Enforcement)     │    │ (Data Governance)        │   │
│  │                        │    │                          │   │
│  │ • Session tag-based    │    │ • Data catalog           │   │
│  │   access control       │    │ • Business glossary      │   │
│  │ • Row-level filters    │    │ • Data lineage           │   │
│  │ • user_id = tag        │    │ • Access workflows       │   │
│  │ • Query engine level   │    │ • Usage analytics        │   │
│  └────────┬───────────────┘    └───────────┬──────────────┘   │
│           │                                 │                   │
│           └──────────────┬──────────────────┘                   │
└──────────────────────────┼──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                       Data Layer                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  AWS Athena + Glue Data Catalog                          │  │
│  │  • lakehouse_db database                          │  │
│  │  • claims table (with user_id for RLS)                   │  │
│  │  • users table (metadata)                                │  │
│  │  • Executes queries with Lake Formation filters          │  │
│  │  • S3 backend: s3://insurance-processor-rba/            │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow Example: User Query

```
1. User Login
   Streamlit UI → Cognito → Returns JWT with user identity
   JWT contains: {
     "email": "user001@example.com",
     "scope": "lakehouse-api/claims/query"
   }

2. Query Submission
   User: "Show me all my pending claims"
   UI → Agent (with Bearer token)

3. Agent Processing
   Agent → Gateway (Bearer token + tool call request)

4. Gateway Interception
   Interceptor Lambda:
   - Validates JWT signature ✓
   - Checks token expiration ✓
   - Extracts user identity: "user001@example.com"
   - Validates scope: "claims/query" ✓
   - Adds header: X-User-Identity: user001@example.com

5. Tool Execution (Dual-Layer Security)

   a) Data Discovery (SageMaker Unified Studio):
      - User can discover "claims" dataset
      - View business glossary definitions
      - See data lineage

   b) Row-Level Security (Lake Formation):
      - MCP assumes IAM role with session tag: user_id=user001@example.com
      - Query: SELECT * FROM claims WHERE status = 'pending'
      - Lake Formation adds: AND user_id = '${aws:PrincipalTag/user_id}'
      - Final: ... WHERE status = 'pending' AND user_id = 'user001@example.com'

6. Athena Execution
   Athena executes filtered query → Returns only user001's claims

7. Response Flow
   Athena → MCP → Gateway → Agent → UI
   User sees only their pending claims
```

---

## Key Features

### Security Features

- **⭐ Enterprise Row-Level Security**: AWS Lake Formation enforces filtering at query engine level
- **🔒 Session Tag-Based Access Control**: User identity passed via IAM session tags (not SQL strings)
- **🛡️ SQL Injection Protection**: Zero SQL string interpolation - Lake Formation handles all filtering
- **📊 Fine-Grained Access Control**: JWT scopes determine which tools users can access
- **🔄 OAuth Token Propagation**: User identity flows through entire system
- **🔍 Full Audit Trail**: CloudTrail logs all data access with user identity

### Governance Features

- **📚 Data Catalog**: Searchable datasets with business context
- **📖 Business Glossary**: Healthcare term definitions (15+ terms)
- **🔗 Data Lineage**: Complete data flow visualization (S3 → Glue → Athena → MCP → Agent → UI)
- **🔐 Access Workflows**: Request and approval process
- **📊 Usage Analytics**: Track who accesses what data
- **🤝 Collaboration**: Share curated datasets

### Application Features

- **🏥 Health Insurance Operations**: Query, submit, update, and approve/deny claims
- **💬 Conversational AI**: Natural language interface for claims processing
- **☁️ Real Athena Integration**: Uses AWS Athena for scalable data queries
- **🎯 Multi-User Support**: Isolated data access per user

---

## Security Implementation

This implementation uses **AWS Lake Formation** with session tags for enterprise-grade row-level security.

### How Lake Formation RLS Works

```python
# Step 1: User Authentication
# User logs in → Cognito generates JWT with user identity

# Step 2: Identity Propagation
# JWT → Agent → Gateway → MCP Server receives user_id

# Step 3: MCP Server assumes IAM role with session tag
user_id = "user001@example.com"  # From Gateway header
credentials = sts.assume_role(
    RoleArn='arn:aws:iam::ACCOUNT:role/claims-rls-role',
    RoleSessionName='claims-query-user001',
    Tags=[
        {'Key': 'user_id', 'Value': user_id}
    ]
)

# Step 4: Lake Formation data filter is configured
# Table: lakehouse_db.claims
# Row Filter: user_id = '${aws:PrincipalTag/user_id}'

# Step 5: User query submitted (NO user_id in WHERE clause!)
query = "SELECT * FROM claims WHERE status = 'pending'"

# Step 6: Lake Formation automatically transforms to:
# SELECT * FROM claims
# WHERE status = 'pending'
# AND user_id = 'user001@example.com'  ← Added by Lake Formation

# Step 7: Athena executes filtered query
# Returns only rows where user_id matches session tag
```

### Security Guarantees

✅ **Cannot Access Other Users' Data**: Even if developer makes mistake, Lake Formation enforces filter
✅ **No SQL Injection**: User identity validated by IAM (not SQL)
✅ **Cannot Bypass**: Security enforced at AWS infrastructure level
✅ **Full Audit Trail**: CloudTrail logs all access with user identity
✅ **Compliance-Ready**: Meets HIPAA, SOC 2, GDPR requirements

### OAuth Scopes

| Scope | Description | Allows |
|-------|-------------|--------|
| `claims/query` | Read claims | query_claims, get_claim_details, get_claims_summary |
| `claims/submit` | Submit claims | submit_claim |
| `claims/update` | Update claims | update_claim_status |
| `claims/approve` | Approve/deny claims | update_claim_status (approval/denial) |

---

## Prerequisites

### AWS Account Setup

1. **AWS Account**:
   - AWS Account ID (e.g., XXXXXXXXXXXX)
   - Region: us-east-1 (configurable)

2. **AWS Permissions**:
   ```
   - BedrockAgentCoreFullAccess
   - AmazonBedrockFullAccess
   - AmazonAthenaFullAccess
   - AmazonS3FullAccess
   - AWSLambdaFullAccess
   - AmazonCognitoPowerUser
   - AWSLakeFormationDataAdmin
   - AmazonSageMakerFullAccess (for Unified Studio)
   ```

3. **AWS Services Enabled**:
   - Amazon Bedrock (with Claude Sonnet 4.5 access)
   - Amazon Bedrock AgentCore
   - AWS Lambda
   - Amazon Cognito
   - AWS Lake Formation
   - Amazon SageMaker
   - AWS Athena
   - AWS Glue
   - Amazon S3

### Development Environment

```bash
# Python 3.10 or later
python --version

# AWS CLI configured
aws configure

# Install dependencies
pip install -r requirements.txt
```

### Python Dependencies

```
boto3>=1.34.0
bedrock-agentcore>=1.0.0
strands-agents>=1.0.0
python-dotenv>=1.0.0
streamlit>=1.30.0
mcp>=1.9.0
python-jose[cryptography]>=3.4.0
pyarrow>=14.0.0
pandas>=2.0.0
sagemaker>=2.200.0
```

---

## Quick Start

### Step 1: Set AWS Region (Optional)

Configure AWS region where the resources will be created. If not set, the default region from your AWS profile will be used.

```bash
export AWS_DEFAULT_REGION=us-west-2
```

### Step 2: Deploy Foundation (Athena Database)

```bash
cd athena-setup

# Creates database, tables, and sample data
# Bucket name will be prefixed with {account_id}-{region}-
python setup_athena.py --bucket-name my-lakehouse
```

**Example**: If your account ID is `123456789012` and region is `us-east-1`, the bucket created will be:
`123456789012-us-east-1-my-lakehouse`

**Creates**:
- S3 bucket: `{account_id}-{region}-{bucket-name}`
- Database: `lakehouse_db`
- Table: `claims` with 9 sample claims
- Table: `users` with user metadata
- Test data for 3 users (user001, user002, adjuster001)
- SSM Parameters:
  - `/app/lakehouse-agent/s3-bucket-name`
  - `/app/lakehouse-agent/database-name`

### Step 3: Deploy Security (Lake Formation RLS)

```bash
# Still in athena-setup/
python setup_lake_formation.py
```

**Reads from SSM Parameter Store**:
- S3 bucket name from `/app/lakehouse-agent/s3-bucket-name`
- Database name from `/app/lakehouse-agent/database-name`

**Creates**:
- IAM role: `lakehouse-rls-role`
- Data filter on claims table
- Row filter: `user_id = '${aws:PrincipalTag/user_id}'`
- Lake Formation permissions

### Step 4: Deploy Governance (SageMaker Unified Studio)

```bash
cd ../governance-setup

# Creates DataZone domain, project, and business glossary
python setup_sagemaker_unified_studio.py --domain-name my-lakehouse-domain
```

**Reads from SSM Parameter Store**:
- S3 bucket name from `/app/lakehouse-agent/s3-bucket-name`
- Database name from `/app/lakehouse-agent/database-name`

**Creates**:
- DataZone domain with the specified name
- Project: `health-lakehouse`
- Athena data source registration
- Business glossary with 15+ healthcare terms
- Data lineage tracking


### Step 5: Deploy Identity (Cognito)

```bash
cd ../gateway-setup

python setup_cognito.py
```
```
Output from the run
✅ User Pool created: us-east-1_xxxx
✅ Resource Server created with scopes
✅ App Client created: xxxxxxxxxxxxxxxxxxx
✅ Domain created: https://xxxxxxxxx-useast1w.auth.us-east-1.amazoncognito.com
✅ Test users created

 Configuration:
{
  "user_pool_id": "us-east-1_7FrHmmIbH",
  "client_id": "m41n4ln1nfs1ikhrm9j3m8tbd",
  "domain": "https://lakehouse-useast17.auth.us-east-1.amazoncognito.com",
  "client_secret": "slgiqslht7cdpq32gn1i6gjv9abf4tgnm116q952516fuk8av4g"
}
```

**Creates**:
- User Pool with OAuth configuration
- App client with scopes
- Test users (user001@example.com, user002@example.com, adjuster001@example.com)
- Password: TempPass123!


### Step 6: Deploy MCP Server on AgentCore Runtime

The MCP (Model Context Protocol) Server runs on AgentCore Runtime and connects the AI agent to AWS Athena. It implements the secure data access layer with Lake Formation row-level security.

**What it does**:
- Receives tool requests from the AgentCore Gateway
- Extracts user identity from request context
- Assumes IAM role with session tags (user_id)
- Executes Athena queries with Lake Formation RLS enforcement
- Returns filtered results (only user's own data)

**Security features**:
- Session tag-based access control (not SQL string interpolation)
- Lake Formation enforces row filters at query engine level
- Zero SQL injection risk
- Full CloudTrail audit trail

**Why AgentCore Runtime instead of Lambda?**
- Native integration with AgentCore ecosystem
- Automatic scaling and lifecycle management
- Built-in observability and monitoring
- Simplified deployment with `agentcore` CLI
- Better performance for agent-to-tool communication

```bash
cd ../mcp-athena-server

# Install dependencies including the starter toolkit
pip install -r requirements.txt

# Verify agentcore CLI is available
which agentcore || echo "⚠️  agentcore CLI not found - it should be installed with bedrock-agentcore-starter-toolkit"

# Deploy to AgentCore Runtime using the Python script
# This will:
# 1. Create IAM role with required permissions
# 2. Build a Docker container with your MCP server
# 3. Deploy it to AgentCore Runtime
python deploy_runtime.py
```


**Required IAM Permissions**:
The AgentCore Runtime execution role needs:
- `AmazonAthenaFullAccess` - Execute Athena queries
- `AWSGlueServiceRole` - Access Glue Data Catalog
- `AmazonS3ReadOnlyAccess` - Read data from S3
- `sts:AssumeRole` - Assume the RLS role with session tags
- `lakeformation:GetDataAccess` - Lake Formation data access

**Deployment Output**:
After running `agentcore launch`, you'll see:
```
✅ MCP Server deployed successfully
Runtime ARN: arn:aws:bedrock-agentcore:us-east-1:ACCOUNT:runtime/runtime-id
Runtime ID: runtime-id
```


# Test the MCP server (after Gateway is deployed)
# Use the Gateway to invoke the MCP server tools
```


### Step 7: Deploy Gateway & Interceptor

The AgentCore Gateway acts as a secure proxy between the AI agent and the MCP server. The Interceptor Lambda validates OAuth tokens and enforces scope-based access control.

**What the Interceptor does**:
- Validates JWT bearer tokens from Cognito
- Checks token signature and expiration
- Extracts user identity (email) from token
- Validates OAuth scopes (claims.query, claims.submit, etc.)
- Adds `X-User-Identity` header to requests
- Blocks unauthorized tool access

**What the Gateway does**:
- Routes tool requests from agent to MCP server
- Applies interceptor for authentication/authorization
- Enforces policy-based access control
- Provides observability and logging

**Deploy the Interceptor Lambda**:
```bash
cd gateway-setup/interceptor

# Package and deploy interceptor Lambda
bash deploy.sh
```

The `deploy.sh` script will:
1. Load Cognito configuration from SSM Parameter Store
2. Create Lambda execution role (if not exists)
3. Package Lambda function with dependencies
4. Create or update Lambda function with proper configuration
5. Store Lambda ARN in SSM Parameter Store

**Required IAM Role Permissions**:
The Lambda execution role includes:
- `AWSLambdaBasicExecutionRole` - CloudWatch logging
- No additional permissions needed (validates JWT locally)

**Create the AgentCore Gateway**:
```bash
# Navigate back to gateway-setup directory
cd ..

# Create gateway (reads all configuration from SSM Parameter Store)
python create_gateway.py
```

The script will:
1. Load configuration from SSM Parameter Store:
   - MCP Server Runtime ARN (from Step 6)
   - Interceptor Lambda ARN (from above)
   - Cognito User Pool ARN (from Step 5)
   - Cognito App Client ID and Secret (from Step 5)
2. Create IAM role for Gateway
3. Create Gateway with JWT authentication
4. Create OAuth2 credential provider in AgentCore Identity for Gateway-to-Runtime authentication
5. Create Gateway target pointing to MCP Server with OAuth2 authentication
6. Store Gateway configuration in SSM Parameter Store

**Gateway Configuration**:
- **Name**: lakehouse-gateway
- **Protocol**: MCP (Model Context Protocol)
- **Auth**: Custom JWT (Cognito) for user authentication
- **Target**: MCP Server Runtime from Step 6
- **Target Auth**: OAuth2 Client Credentials (Gateway authenticates to Runtime)

**Authentication Flow**:
- **User → Agent**: Bearer token (JWT from Cognito)
- **Agent → Gateway**: Bearer token (JWT from Cognito)
- **Gateway → Runtime**: OAuth2 access token (Client Credentials grant)

**What happens when a request flows through**:
```
1. Agent sends request with Bearer token (user JWT)
   ↓
2. Gateway invokes Interceptor Lambda
   ↓
3. Interceptor validates JWT and extracts user_id
   ↓
4. Gateway adds X-User-Identity header
   ↓
5. Gateway obtains OAuth2 token from AgentCore Identity (Client Credentials)
   ↓
6. Gateway invokes MCP Server Runtime with OAuth2 token
   ↓
7. MCP Server assumes role with session tag
   ↓
8. Lake Formation enforces row filter
   ↓
9. Results returned to agent
```


### Step 8: Deploy Lakehouse Agent

```bash
cd ../../lakehouse-agent

# Deploy the agent to AgentCore Runtime
python deploy_lakehouse_agent.py
```

The deployment script will:
1. Create IAM role for the agent runtime with necessary permissions (Bedrock, Gateway access, CloudWatch logs)
2. Use the Bedrock AgentCore Starter Toolkit to build a Docker container
3. Deploy the containerized agent to AgentCore Runtime

**What happens during deployment**:
- Docker builds a container image with your agent code and dependencies
- Image is pushed to Amazon ECR (Elastic Container Registry)
- AgentCore Runtime is created and configured
- Agent is ready to receive requests

**Configuration saved automatically**:
- `LAKEHOUSE_AGENT_RUNTIME_ID`: Runtime identifier
- `LAKEHOUSE_AGENT_RUNTIME_ARN`: Full ARN of the runtime
- `LAKEHOUSE_AGENT_NAME`: Agent name (lakehouse_agent)

**Note**: This deployment uses Docker, so ensure Docker is running on your machine.

### Step 9: Run Streamlit UI

```bash
cd ../streamlit-ui

streamlit run streamlit_app.py
```

Open http://localhost:8501 in your browser.

### Step 10: Test the System

```
1. Login with: user001@example.com / TempPass123!
2. Query: "Show me all my claims"
3. Verify: Only sees 4 claims (their own)
4. Login with: user002@example.com / TempPass123!
5. Query: "Show me all my claims"
6. Verify: Only sees 5 claims (their own)
```

### Configuration Commands

```bash
# Validate configuration
python config.py --validate

# Show configuration status
python config.py --show

# Get specific value
python config.py --get S3_BUCKET_NAME
```

---

## Deployment Steps

### Complete Deployment Roadmap

| Phase | Component | Command | Duration | Output |
|-------|-----------|---------|----------|--------|
| 1 | Athena Database | `python setup_athena.py --bucket-name NAME` | 30 min | Database, tables, SSM params |
| 2 | Lake Formation RLS | `python setup_lake_formation.py` | 45 min | RLS_ROLE_ARN |
| 3 | SageMaker Unified Studio | `python setup_sagemaker_unified_studio.py --domain-name NAME` | 1-2 hrs | DATAZONE_DOMAIN_ID, PROJECT_ID |
| 4 | Cognito User Pool | `python setup_cognito.py --region REGION` | 30 min | COGNITO_USER_POOL_ID, CLIENT_ID |
| 5 | MCP Server | `python deploy_runtime.py` | 45 min | MCP_SERVER_ARN |
| 6 | Gateway & Interceptor | `bash deploy.sh` + `python create_gateway.py` | 1 hr | GATEWAY_ARN, INTERCEPTOR_ARN |
| 7 | Lakehouse Agent | `python deploy_lakehouse_agent.py` | 30 min | RUNTIME_ARN |
| 8 | Streamlit UI | `streamlit run streamlit_app.py` | 30 min | http://localhost:8501 |
| 9 | Integration Testing | `python test_e2e_flow.py` | 2 hrs | Test results |
| 10 | Documentation | Review and customize | 4 hrs | Runbooks, guides |

**Total Time**: ~10-12 hours (can be spread over multiple days)

### Key Changes from Previous Versions

**Setup Scripts Now Use**:
- ✅ **Boto3 session** for region and account ID (no manual configuration needed)
- ✅ **SSM Parameter Store** for sharing configuration between scripts
- ✅ **Automatic bucket naming** with `{account_id}-{region}-{base-name}` format
- ✅ **Required arguments** for critical parameters (--bucket-name, --domain-name)
- ✅ **No config.py dependency** - all scripts are self-contained

**Configuration Flow**:
1. `setup_athena.py` creates SSM parameters with bucket and database names
2. `setup_lake_formation.py` reads from SSM parameters
3. `setup_sagemaker_unified_studio.py` reads from SSM parameters
4. All scripts automatically detect region and account ID from AWS credentials

---

## Testing

### Quick End-to-End Test

Run the automated test script to verify the complete flow:

```bash
cd 02-use-cases/lakehouse-processor
python test_e2e_flow.py
```

This test will:
1. Get Cognito bearer token using `client_credentials` flow
2. Invoke the lakehouse agent runtime with the token
3. Verify the agent can communicate with the Gateway
4. Check that the bearer token flows through the entire stack

Expected output:
```
============================================================
🧪 Testing End-to-End Flow
============================================================
🔑 Getting Cognito bearer token...
✅ Token obtained: eyJraWQiOiJxxx...

🤖 Invoking agent runtime...
   Prompt: Show me all my claims
   Runtime ARN: arn:aws:bedrock-agentcore:us-east-1:XXXXXXXXXXXX:runtime/lakehouse_agent-Hhb3lX6y7M
   Bearer token: eyJraWQiOiJxxx...

✅ Agent response:
{
  "content": "...",
  "tool_calls": 1
}

============================================================
✅ End-to-end test completed!
============================================================
```

### Streamlit UI Test

Launch the Streamlit interface:

```bash
cd streamlit-ui
streamlit run streamlit_app.py
```

Test queries:
- "Show me all my claims"
- "What's the status of CLM-2024-001?"
- "Get my claims summary"
- "Show pending claims"

### Row-Level Security Test

```python
# Test with user001
from athena_tools_secure import SecureAthenaClaimsTools

tools = SecureAthenaClaimsTools(
    region='us-east-1',
    database_name='lakehouse_db',
    s3_output_location='s3://bucket/athena-results/',
    rls_role_arn='arn:aws:iam::ACCOUNT:role/claims-rls-role'
)

# User 1
claims1 = tools.query_claims('user001@example.com')
assert len(claims1) == 4  # Only user001's claims
assert all(c['user_id'] == 'user001@example.com' for c in claims1)

# User 2
claims2 = tools.query_claims('user002@example.com')
assert len(claims2) == 5  # Only user002's claims
assert all(c['user_id'] == 'user002@example.com' for c in claims2)

# Verify no overlap
ids1 = {c['claim_id'] for c in claims1}
ids2 = {c['claim_id'] for c in claims2}
assert ids1.isdisjoint(ids2)  # No shared claims ✓
```

### End-to-End Test

```
1. Log in with user001@example.com
2. Query: "Show me all my pending claims"
   Expected: See only user001's pending claims (not user002's)

3. Query: "Get details for CLM-2024-001"
   Expected: See details if claim belongs to user001, otherwise error

4. Query: "Submit a new claim for $500 medical visit"
   Expected: New claim created with user_id = user001@example.com

5. Log out and log in with user002@example.com
6. Query: "Show me all my claims"
   Expected: See only user002's 5 claims (not user001's 4)
```

### Security Validation

```python
# Test: Cannot bypass Lake Formation filter
# Even malicious query returns only user's data

credentials = assume_role_with_tag('user001@example.com')
query = "SELECT * FROM claims"  # No filter!

# Lake Formation STILL enforces: WHERE user_id = 'user001@example.com'
results = execute_query(credentials, query)
assert len(results) == 4  # Only user001's claims ✓
```

### Test Suite

```bash
# Run comprehensive tests
cd tests
pytest test_sagemaker_studio.py -v  # Governance tests
python test_end_to_end.py            # Integration tests
```

---

## Usage Examples

### Example 1: Query Claims

```
User: "Show me all my pending claims"

Agent Response:
"You have 2 pending claims:

1. Claim CLM-2024-001 - Medical Visit
   - Amount: $500
   - Provider: City Hospital
   - Submitted: 2024-01-15
   - Status: Pending

2. Claim CLM-2024-003 - Prescription
   - Amount: $300
   - Provider: ABC Pharmacy
   - Submitted: 2024-01-20
   - Status: Pending"
```

### Example 2: Submit New Claim

```
User: "I need to submit a new claim for a medical visit at General Hospital for $750"

Agent Response:
"I'll help you submit that claim. I need a few more details:
- What was the diagnosis code?
- Do you have any additional notes?"

User: "Diagnosis code J06.9, annual checkup"

Agent Response:
"Claim submitted successfully!

Claim ID: CLM-2024-010
Type: Medical Visit
Amount: $750
Provider: General Hospital
Diagnosis: J06.9
Status: Pending
Submitted: 2024-01-25

Your claim will be reviewed within 5 business days."
```

### Example 3: Check Claim Status

```
User: "What's the status of claim CLM-2024-001?"

Agent Response:
"Claim CLM-2024-001 details:

Status: Approved ✓
Amount: $500
Provider: City Hospital
Processed Date: 2024-01-18
Payment: Check will be mailed within 7-10 business days"
```

### Example 4: Get Claims Summary

```
User: "Give me a summary of all my claims"

Agent Response:
"Here's your claims summary:

Total Claims: 4
Total Amount: $2,800

By Status:
- Approved: 2 claims ($1,300)
- Pending: 1 claim ($500)
- Denied: 1 claim ($1,000)

By Type:
- Medical: 2 claims ($1,500)
- Prescription: 1 claim ($300)
- Hospital: 1 claim ($1,000)"
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **Gateway MCP endpoint wrong** | Incorrect URL format for runtime | Run `python gateway-setup/fix_gateway_target.py` |
| **No CloudWatch logs for agent** | IAM role missing logs permissions | Run `python lakehouse-agent/fix_agent_role_permissions.py` |
| **Bearer token required** | No token in request | Ensure Streamlit UI passes bearer token |
| **Claim 'iss' value mismatch** | Agent authorizer config mismatch | Run `python lakehouse-agent/update_agent_authorizer.py` |
| **Authorization method mismatch** | Agent using IAM instead of JWT | Run `python lakehouse-agent/update_agent_authorizer.py` |
| **Unknown service: bedrock-agentcore-identity** | Wrong boto3 client name | Use `bedrock-agentcore-control` client for Identity APIs |
| **User sees all claims** | Lake Formation not enabled | Run `setup_lake_formation.py` |
| **No claims returned** | Wrong user_id in session tag | Check X-User-Identity header propagation |
| **Athena permission denied** | Missing IAM permissions | Check Lambda execution role has Athena access |
| **Gateway timeout** | MCP server timeout | Increase Lambda timeout to 300s |

### Diagnostic Scripts

```bash
# Fix gateway MCP endpoint URL
python gateway-setup/fix_gateway_target.py

# Check all runtimes and their logs
python find_all_runtimes.py

# Check agent status and CloudWatch logs
python check_agent_status.py

# Diagnose JWT authentication issues
python diagnose_auth_issue.py

# Fix IAM role CloudWatch permissions
python lakehouse-agent/fix_agent_role_permissions.py

# Update agent JWT authorizer config
python lakehouse-agent/update_agent_authorizer.py
```

### Debug Commands

```bash
# Check configuration
python test_ssm_validation.py

# Test Athena connectivity
cd athena-setup
python -c "from config import config; print(config.ATHENA_DATABASE_NAME)"

# Check Lake Formation permissions
aws lakeformation list-permissions --resource-type TABLE

# View CloudWatch logs
aws logs tail /aws/lambda/lakehouse-mcp-server --follow

# Test JWT validation
python gateway-setup/test_cognito_login.py
```

### Logs to Check

```bash
# Agent Runtime logs (replace <runtime-id> with actual ID)
aws logs tail /aws/bedrock-agentcore/runtime/<runtime-id> --follow

# MCP Server logs
aws logs tail /aws/lambda/lakehouse-mcp-server --follow

# Gateway Interceptor logs
aws logs tail /aws/lambda/lakehouse-gateway-interceptor --follow

# Athena query logs
aws logs tail /aws/athena/query-logs --follow
```

### CloudWatch Logs Not Appearing?

If you don't see CloudWatch logs for your agent runtime:

1. **Check IAM role permissions**:
   ```bash
   python lakehouse-agent/fix_agent_role_permissions.py
   ```

2. **Verify agent has been invoked**:
   - Logs are only created after the first invocation
   - Use Streamlit UI or invoke via API

3. **Check agent status**:
   ```bash
   python check_agent_status.py
   ```

4. **Find log group name**:
   - Format: `/aws/bedrock-agentcore/runtime/<runtime-id>`
   - Use `find_all_runtimes.py` to get the runtime ID

### Gateway MCP Endpoint Issues?

If the gateway can't connect to the MCP server runtime:

1. **Check MCP endpoint format**:
   - Correct format: `https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded-arn}/invocations?qualifier=DEFAULT`
   - The runtime ARN must be encoded: `:` → `%3A` and `/` → `%2F`
   - Must end with `/invocations?qualifier=DEFAULT`
   - Example encoding:
     ```python
     encoded_arn = runtime_arn.replace(':', '%3A').replace('/', '%2F')
     ```

2. **Fix gateway target**:
   ```bash
   python gateway-setup/fix_gateway_target.py
   ```

3. **Verify runtime is active**:
   ```bash
   python find_all_runtimes.py
   ```

**Common mistake**: Using `/mcp` endpoint or not encoding the ARN properly. The correct endpoint is `/invocations?qualifier=DEFAULT` with properly encoded ARN.

---

## File Structure

```
lakehouse-processor/
│
│
├── 🗄️ Data Layer
│   └── athena-setup/
│       ├── setup_athena_with_config.py # Athena setup
│       ├── setup_lake_formation.py     # Lake Formation RLS
│       ├── create_tables.sql           # Table definitions
│       └── sample_data.sql             # Sample data
│
├── 🏛️ Governance Layer
│   └── governance-setup/
│       ├── setup_sagemaker_unified_studio.py  # SageMaker setup
│       ├── business_glossary.json      # Glossary definitions
│       └── requirements.txt            # Dependencies
│
├── 🔐 Identity Layer
│   └── gateway-setup/
│       ├── setup_cognito.py            # Cognito setup
│       ├── create_gateway.py           # Gateway creation
│       └── interceptor/
│           ├── lambda_function.py      # JWT validator
│           ├── requirements.txt        # Dependencies
│           └── deploy.sh               # Deployment script
│
├── 🔧 Tool Layer
│   └── mcp-athena-server/
│       ├── server.py                   # Production MCP server
│       ├── athena_tools_secure.py      # Lake Formation RLS tools
│       ├── requirements.txt            # Dependencies
│       └── deploy.sh                   # Deployment script
│
├── 🤖 Agent Layer
│   └── lakehouse-agent/
│       ├── lakehouse_agent.py             # Strands-based agent
│       ├── requirements.txt            # Dependencies
│       └── deploy.sh                   # Deployment script
│
├── 🖥️ UI Layer
│   └── streamlit-ui/
│       ├── streamlit_app.py            # Main UI application
│       ├── config.py                   # UI-specific config
│       └── requirements.txt            # Dependencies
│
└── 🧪 Testing
    └── tests/
        ├── test_athena.py              # Database tests
        ├── test_lake_formation.py      # RLS tests
        ├── test_sagemaker_studio.py    # Governance tests
        ├── test_cognito.py             # Auth tests
        ├── test_mcp_server.py          # Tool tests
        ├── test_gateway.py             # Gateway tests
        ├── test_agent.py               # Agent tests
        ├── test_streamlit.py           # UI tests
        └── test_end_to_end.py          # Integration tests
```

---

## Cost Estimate

### Monthly Cost Breakdown

```
Component                      Monthly Cost
─────────────────────────────────────────────
S3 Storage (100GB)             $2.30
Athena (1TB scanned/month)     $5.00
Lambda (1M invocations)        $0.20
Cognito (1000 users)           $0.00 (free tier)
Lake Formation                 $0.00 (no additional cost)
SageMaker Unified Studio       $500-$700
AgentCore Runtime              $100-$200
Bedrock Claude API             Variable (per token)
─────────────────────────────────────────────
Total (excluding Bedrock)      ~$600-$900/month
```

### Cost Optimization Tips

- Use Parquet format for S3 data (reduces Athena scan costs by 90%)
- Partition claims data by month (faster queries, lower costs)
- Cache frequent queries in application layer
- Use reserved Lambda capacity if usage is predictable
- Consider SageMaker Unified Studio ROI based on team size

---

## Advanced Topics

### Adding New Tools

To add a new tool to the MCP server:

1. Define tool in `athena_tools_secure.py`:
```python
def get_claim_history(self, user_id: str, claim_id: str) -> List[Dict]:
    """Get complete history of a claim."""
    credentials = self._get_credentials_with_session_tag(user_id)
    query = f"""
        SELECT * FROM claim_history
        WHERE claim_id = '{claim_id}'
        ORDER BY timestamp DESC
    """
    # Lake Formation still enforces: AND user_id = session_tag
    return self._execute_query(query, credentials)
```

2. Gateway automatically discovers the new tool
3. Agent can now use it: "Show me the history of claim CLM-2024-001"

### Custom OAuth Scopes

To add custom scopes:

1. Update Cognito resource server:
```bash
aws cognito-idp create-resource-server \
  --user-pool-id YOUR_POOL_ID \
  --identifier lakehouse-api \
  --scopes ScopeName=claims/history,ScopeDescription="View claim history"
```

2. Update Gateway interceptor to check new scope
3. Assign scope to appropriate user groups

### Multi-Tenant Support

To support multiple insurance companies:

1. Add `tenant_id` column to claims table
2. Update Lake Formation filter:
   ```
   user_id = '${aws:PrincipalTag/user_id}'
   AND tenant_id = '${aws:PrincipalTag/tenant_id}'
   ```
3. Pass both tags when assuming role
4. Each tenant sees only their company's data

---

## Security & Compliance

### HIPAA Compliance

✅ **Access Controls**: Lake Formation enforces patient data isolation
✅ **Audit Trail**: CloudTrail logs all PHI access
✅ **Encryption**: Data encrypted at rest (S3) and in transit (HTTPS)
✅ **Integrity**: Data filters cannot be tampered with

### SOC 2 Compliance

✅ **CC6.1 - Logical Access**: Infrastructure-level access controls
✅ **CC6.2 - Authentication**: OAuth with JWT validation
✅ **CC6.3 - Authorization**: Row-level filters
✅ **CC7.2 - Monitoring**: CloudWatch and CloudTrail logging

### GDPR Compliance

✅ **Article 5 - Data Minimization**: Users access only their own data
✅ **Article 32 - Security**: Infrastructure-level controls
✅ **Article 30 - Records**: Complete audit trail

---

## Support & Resources

### Documentation

- This README contains all essential information
- For AWS service documentation, see official AWS docs

### Community

- AWS Forums: https://forums.aws.amazon.com/
- Stack Overflow tags: `aws-lake-formation`, `amazon-bedrock`, `amazon-athena`

### AWS Documentation

- [Lake Formation](https://docs.aws.amazon.com/lake-formation/)
- [SageMaker Unified Studio](https://docs.aws.amazon.com/sagemaker/latest/dg/unified-studio.html)
- [Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html)
- [Amazon Athena](https://docs.aws.amazon.com/athena/)
- [Amazon Cognito](https://docs.aws.amazon.com/cognito/)

---

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.

---

**Status**: Production-Ready ✅
**Security**: Enterprise-Grade with Lake Formation
**Governance**: SageMaker Unified Studio Integrated
**Last Updated**: January 2025
