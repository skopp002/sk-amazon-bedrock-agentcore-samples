#!/usr/bin/env python3
"""
SageMaker Unified Studio (DataZone) Setup for Lakehouse Agent

This script sets up data governance infrastructure including:
- DataZone domain for data governance
- Project for health lakehouse data
- Environment for analytics
- Athena data source registration
- Business glossary with healthcare terms
- Data lineage tracking

Prerequisites:
- AWS credentials configured
- Lake Formation already set up (run setup_lake_formation.py first)
- Athena database exists (run setup_athena_with_config.py first)
- config.py with required values

Usage:
    python setup_sagemaker_unified_studio.py

Outputs ARNs to update in SSM Parameter Store:
- DATAZONE_DOMAIN_ID
- DATAZONE_PROJECT_ID
- DATAZONE_ENVIRONMENT_ID
- DATAZONE_DATA_SOURCE_ID
"""

import boto3
import json
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config


class SageMakerUnifiedStudioSetup:
    """Sets up SageMaker Unified Studio (DataZone) for data governance."""

    def __init__(self):
        """Initialize AWS clients and configuration."""
        self.region = config.AWS_REGION
        self.account_id = config.AWS_ACCOUNT_ID
        self.athena_database = config.ATHENA_DATABASE_NAME
        self.s3_bucket = config.S3_BUCKET_NAME

        # Initialize AWS clients
        self.datazone = boto3.client('datazone', region_name=self.region)
        self.iam = boto3.client('iam', region_name=self.region)
        self.sts = boto3.client('sts', region_name=self.region)

        print(f"Initialized SageMaker Unified Studio setup for account {self.account_id}")

    def create_domain_execution_role(self) -> str:
        """
        Create IAM role for DataZone domain execution.

        Returns:
            Role ARN
        """
        role_name = 'DataZoneDomainExecutionRole-lakehouse'

        # Trust policy for DataZone
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "datazone.amazonaws.com"
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
                        "glue:GetDatabase",
                        "glue:GetTable",
                        "glue:GetTables",
                        "glue:GetPartition",
                        "glue:GetPartitions",
                        "athena:ListWorkGroups",
                        "athena:GetWorkGroup",
                        "athena:ListDataCatalogs",
                        "athena:GetDataCatalog",
                        "s3:ListBucket",
                        "s3:GetObject",
                        "lakeformation:GetDataAccess",
                        "lakeformation:GrantPermissions",
                        "lakeformation:ListPermissions"
                    ],
                    "Resource": "*"
                }
            ]
        }

        try:
            # Create role
            print(f"Creating IAM role: {role_name}")
            response = self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description='DataZone domain execution role for lakehouse data governance'
            )
            role_arn = response['Role']['Arn']

            # Attach inline policy
            self.iam.put_role_policy(
                RoleName=role_name,
                PolicyName='DataZonePermissions',
                PolicyDocument=json.dumps(permissions_policy)
            )

            print(f"✅ Created IAM role: {role_arn}")
            time.sleep(10)  # Wait for IAM eventual consistency
            return role_arn

        except self.iam.exceptions.EntityAlreadyExistsException:
            print(f"ℹ️  Role {role_name} already exists, retrieving ARN")
            response = self.iam.get_role(RoleName=role_name)
            return response['Role']['Arn']

    def create_domain(self, role_arn: str) -> str:
        """
        Create DataZone domain for data governance.

        Args:
            role_arn: Domain execution role ARN

        Returns:
            Domain ID
        """
        domain_name = config.DATAZONE_DOMAIN_NAME or 'lakehouse-domain'

        try:
            print(f"Creating DataZone domain: {domain_name}")
            response = self.datazone.create_domain(
                name=domain_name,
                description='Health lakehouse data data governance and cataloging',
                domainExecutionRole=role_arn
                # Note: kmsKeyIdentifier omitted to use default encryption
                # If you need a specific KMS key, provide the full ARN:
                # arn:aws:kms:region:account-id:key/key-id
            )

            domain_id = response['id']
            print(f"✅ Created DataZone domain: {domain_id}")
            print(f"   Status: {response['status']}")

            # Wait for domain to be available
            print("   Waiting for domain to be available...")
            self._wait_for_domain_available(domain_id)

            return domain_id

        except Exception as e:
            if 'already exists' in str(e).lower():
                print(f"ℹ️  Domain already exists, listing domains to find ID")
                return self._find_existing_domain(domain_name)
            raise

    def _wait_for_domain_available(self, domain_id: str, timeout: int = 300):
        """Wait for domain to be available."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = self.datazone.get_domain(identifier=domain_id)
                status = response['status']
                if status == 'AVAILABLE':
                    print("   ✅ Domain is available")
                    return
                elif status == 'FAILED':
                    raise Exception(f"Domain creation failed: {response.get('statusReason', 'Unknown')}")
                else:
                    print(f"   Status: {status}, waiting...")
                    time.sleep(10)
            except Exception as e:
                print(f"   Error checking domain status: {e}")
                time.sleep(10)

        raise TimeoutError(f"Domain did not become available within {timeout} seconds")

    def _find_existing_domain(self, domain_name: str) -> str:
        """Find existing domain by name."""
        paginator = self.datazone.get_paginator('list_domains')
        for page in paginator.paginate():
            for domain in page.get('items', []):
                if domain['name'] == domain_name:
                    return domain['id']
        raise Exception(f"Domain {domain_name} not found")

    def create_project(self, domain_id: str) -> str:
        """
        Create DataZone project for health lakehouse data.

        Args:
            domain_id: DataZone domain ID

        Returns:
            Project ID
        """
        project_name = config.DATAZONE_PROJECT_NAME or 'health-lakehouse'

        try:
            print(f"Creating DataZone project: {project_name}")
            response = self.datazone.create_project(
                domainIdentifier=domain_id,
                name=project_name,
                description='Health lakehouse data processing and analytics'
            )

            project_id = response['id']
            print(f"✅ Created DataZone project: {project_id}")
            return project_id

        except Exception as e:
            if 'already exists' in str(e).lower():
                print(f"ℹ️  Project already exists, listing to find ID")
                return self._find_existing_project(domain_id, project_name)
            raise

    def _find_existing_project(self, domain_id: str, project_name: str) -> str:
        """Find existing project by name."""
        paginator = self.datazone.get_paginator('list_projects')
        for page in paginator.paginate(domainIdentifier=domain_id):
            for project in page.get('items', []):
                if project['name'] == project_name:
                    return project['id']
        raise Exception(f"Project {project_name} not found")

    def create_environment_profile(self, domain_id: str, project_id: str) -> str:
        """
        Create environment profile for Athena access.

        Args:
            domain_id: DataZone domain ID
            project_id: Project ID

        Returns:
            Environment profile ID
        """
        try:
            print("Creating environment profile for Athena")
            response = self.datazone.create_environment_profile(
                domainIdentifier=domain_id,
                projectIdentifier=project_id,
                name='athena-analytics-profile',
                description='Environment profile for Athena analytics',
                environmentBlueprintIdentifier='DefaultAthenaEnvironmentBlueprint',
                awsAccountId=self.account_id,
                awsAccountRegion=self.region
            )

            profile_id = response['id']
            print(f"✅ Created environment profile: {profile_id}")
            return profile_id

        except Exception as e:
            print(f"⚠️  Could not create environment profile: {e}")
            print("   You may need to create this manually in the console")
            return None

    def create_environment(self, domain_id: str, project_id: str, profile_id: Optional[str]) -> str:
        """
        Create DataZone environment.

        Args:
            domain_id: DataZone domain ID
            project_id: Project ID
            profile_id: Environment profile ID

        Returns:
            Environment ID
        """
        if not profile_id:
            print("⚠️  Skipping environment creation (no profile)")
            return None

        try:
            print("Creating DataZone environment")
            response = self.datazone.create_environment(
                domainIdentifier=domain_id,
                projectIdentifier=project_id,
                name='claims-analytics-env',
                description='Environment for claims analytics',
                environmentProfileIdentifier=profile_id
            )

            env_id = response['id']
            print(f"✅ Created environment: {env_id}")
            return env_id

        except Exception as e:
            print(f"⚠️  Could not create environment: {e}")
            print("   You may need to create this manually in the console")
            return None

    def register_athena_data_source(self, domain_id: str, project_id: str) -> str:
        """
        Register Athena database as data source.

        Args:
            domain_id: DataZone domain ID
            project_id: Project ID

        Returns:
            Data source ID
        """
        try:
            print(f"Registering Athena data source: {self.athena_database}")
            response = self.datazone.create_data_source(
                domainIdentifier=domain_id,
                projectIdentifier=project_id,
                name='claims-athena-source',
                description=f'Athena data source for {self.athena_database} database',
                type='ATHENA',
                configuration={
                    'athenaConfiguration': {
                        'databaseName': self.athena_database,
                        'workgroupName': config.ATHENA_WORKGROUP
                    }
                },
                enableSetting='ENABLED',
                publishOnImport=True
            )

            source_id = response['id']
            print(f"✅ Registered data source: {source_id}")
            return source_id

        except Exception as e:
            print(f"⚠️  Could not register data source: {e}")
            print(f"   Error details: {str(e)}")
            return None

    def create_business_glossary(self, domain_id: str) -> Dict[str, str]:
        """
        Create business glossary with healthcare insurance terms.

        Args:
            domain_id: DataZone domain ID

        Returns:
            Dict of term names to term IDs
        """
        # Load glossary definitions from file
        glossary_file = Path(__file__).parent / 'business_glossary.json'
        if glossary_file.exists():
            with open(glossary_file) as f:
                terms = json.load(f)
        else:
            # Default terms if file doesn't exist
            terms = [
                {
                    "name": "Claim",
                    "shortDescription": "Request for payment for healthcare services",
                    "longDescription": "A claim is a request for payment submitted by a patient or healthcare provider for medical services rendered. It includes details about the service, cost, and patient information."
                },
                {
                    "name": "Claim Status",
                    "shortDescription": "Current state of claim processing",
                    "longDescription": "The status of a claim in the processing workflow. Valid values: pending (submitted but not reviewed), approved (accepted for payment), denied (rejected), in_review (under investigation)."
                },
                {
                    "name": "Claim Type",
                    "shortDescription": "Category of medical service",
                    "longDescription": "The type of healthcare service covered by the claim. Valid values: medical (doctor visits, procedures), prescription (medication), hospital (inpatient care)."
                },
                {
                    "name": "Diagnosis Code",
                    "shortDescription": "ICD-10 medical diagnosis code",
                    "longDescription": "Standardized ICD-10 code representing the medical diagnosis associated with the claim. Used for billing and statistical purposes."
                },
                {
                    "name": "Provider",
                    "shortDescription": "Healthcare service provider",
                    "longDescription": "The healthcare facility, hospital, clinic, or physician who provided the medical services for this claim."
                },
                {
                    "name": "Claim Amount",
                    "shortDescription": "Dollar amount requested for payment",
                    "longDescription": "The total amount in USD requested for reimbursement for the healthcare services provided. Must be a positive decimal value."
                },
                {
                    "name": "User ID",
                    "shortDescription": "Patient or adjuster identifier",
                    "longDescription": "Unique identifier for the user (patient or claims adjuster). Typically an email address. Used for row-level security to ensure users only see their own claims."
                },
                {
                    "name": "Patient Name",
                    "shortDescription": "Name of the patient receiving care",
                    "longDescription": "Full name of the patient who received the healthcare services covered by this claim."
                }
            ]

        print(f"Creating business glossary with {len(terms)} terms")
        created_terms = {}

        try:
            # Create glossary
            glossary_response = self.datazone.create_glossary(
                domainIdentifier=domain_id,
                name='Healthcare Insurance Glossary',
                description='Standard terminology for health lakehouse data',
                owningProjectIdentifier=domain_id  # Domain-level glossary
            )
            glossary_id = glossary_response['id']
            print(f"✅ Created glossary: {glossary_id}")

            # Create terms
            for term in terms:
                try:
                    term_response = self.datazone.create_glossary_term(
                        domainIdentifier=domain_id,
                        glossaryIdentifier=glossary_id,
                        name=term['name'],
                        shortDescription=term['shortDescription'],
                        longDescription=term.get('longDescription', term['shortDescription'])
                    )
                    term_id = term_response['id']
                    created_terms[term['name']] = term_id
                    print(f"   ✅ Created term: {term['name']}")
                except Exception as e:
                    print(f"   ⚠️  Could not create term '{term['name']}': {e}")

        except Exception as e:
            print(f"⚠️  Could not create glossary: {e}")
            print("   You may need to create this manually in the console")

        return created_terms

    def print_summary(self, domain_id: str, project_id: str, env_id: Optional[str],
                     source_id: Optional[str], glossary_terms: Dict[str, str]):
        """
        Print setup summary with values to add to SSM Parameter Store.

        Args:
            domain_id: DataZone domain ID
            project_id: Project ID
            env_id: Environment ID
            source_id: Data source ID
            glossary_terms: Dict of glossary term IDs
        """
        print("\n" + "=" * 70)
        print("SageMaker Unified Studio Setup Complete!")
        print("=" * 70)

        print("\n📋 Add these values to SSM Parameter Store:\n")
        print(f"aws ssm put-parameter --name lh_datazone_domain_id --value '{domain_id}' --type String --overwrite")
        print(f"aws ssm put-parameter --name lh_datazone_project_id --value '{project_id}' --type String --overwrite")
        if env_id:
            print(f"aws ssm put-parameter --name lh_datazone_environment_id --value '{env_id}' --type String --overwrite")
        if source_id:
            print(f"aws ssm put-parameter --name lh_datazone_data_source_id --value '{source_id}' --type String --overwrite")
        print(f"aws ssm put-parameter --name lh_enable_datazone_integration --value 'true' --type String --overwrite")

        print("\n🔗 Access SageMaker Unified Studio:")
        print(f"https://console.aws.amazon.com/datazone/home?region={self.region}#/domains/{domain_id}")

        print("\n✅ Created Resources:")
        print(f"   • Domain: {domain_id}")
        print(f"   • Project: {project_id}")
        if env_id:
            print(f"   • Environment: {env_id}")
        if source_id:
            print(f"   • Data Source: {source_id}")
        print(f"   • Glossary Terms: {len(glossary_terms)}")

        print("\n📚 Next Steps:")
        print("   1. Update SSM Parameter Store with the values above")
        print("   2. Run: python config.py --validate")
        print("   3. Access SageMaker Unified Studio console to:")
        print("      - Configure data lineage")
        print("      - Set up access workflows")
        print("      - Explore the data catalog")
        print("   4. Continue with deployment (Phase 4+)")

        print("\n" + "=" * 70)


def main():
    """Main setup function."""
    print("=" * 70)
    print("SageMaker Unified Studio (DataZone) Setup")
    print("Lakehouse Agent - Data Governance Layer")
    print("=" * 70)

    # Validate configuration
    if not config.AWS_ACCOUNT_ID or not config.S3_BUCKET_NAME:
        print("\n❌ Error: Missing required configuration")
        print("   Please ensure SSM Parameter Store has:")
        print("   - lh_aws_account_id (auto-detected from STS)")
        print("   - lh_s3_bucket_name")
        print("   - ATHENA_DATABASE_NAME")
        sys.exit(1)

    print(f"\n📋 Configuration:")
    print(f"   AWS Account: {config.AWS_ACCOUNT_ID}")
    print(f"   Region: {config.AWS_REGION}")
    print(f"   Athena Database: {config.ATHENA_DATABASE_NAME}")
    print(f"   S3 Bucket: {config.S3_BUCKET_NAME}")

    # Confirm setup
    response = input("\nProceed with SageMaker Unified Studio setup? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Setup cancelled")
        sys.exit(0)

    # Initialize setup
    setup = SageMakerUnifiedStudioSetup()

    try:
        # Step 1: Create IAM role
        print("\n" + "=" * 70)
        print("Step 1: Creating IAM Role")
        print("=" * 70)
        role_arn = setup.create_domain_execution_role()

        # Step 2: Create domain
        print("\n" + "=" * 70)
        print("Step 2: Creating DataZone Domain")
        print("=" * 70)
        domain_id = setup.create_domain(role_arn)

        # Step 3: Create project
        print("\n" + "=" * 70)
        print("Step 3: Creating Project")
        print("=" * 70)
        project_id = setup.create_project(domain_id)

        # Step 4: Create environment profile
        print("\n" + "=" * 70)
        print("Step 4: Creating Environment Profile")
        print("=" * 70)
        profile_id = setup.create_environment_profile(domain_id, project_id)

        # Step 5: Create environment
        print("\n" + "=" * 70)
        print("Step 5: Creating Environment")
        print("=" * 70)
        env_id = setup.create_environment(domain_id, project_id, profile_id)

        # Step 6: Register data source
        print("\n" + "=" * 70)
        print("Step 6: Registering Athena Data Source")
        print("=" * 70)
        source_id = setup.register_athena_data_source(domain_id, project_id)

        # Step 7: Create business glossary
        print("\n" + "=" * 70)
        print("Step 7: Creating Business Glossary")
        print("=" * 70)
        glossary_terms = setup.create_business_glossary(domain_id)

        # Print summary
        setup.print_summary(domain_id, project_id, env_id, source_id, glossary_terms)

    except Exception as e:
        print(f"\n❌ Error during setup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
