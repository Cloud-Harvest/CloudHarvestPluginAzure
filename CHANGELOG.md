# CHANGELOG

## 0.6.0
- Updated to conform with CloudHarvestCoreTasks 0.9.0
- Fixed some reports
- Added `singleton_keys` to service templates which use keys other than the `UniqueIdentifier`
- Updated `single` service template values to the values defined in `singleton_keys` or the `UniqueIdentifier`

## 0.5.3
- AzureTask will now retry on `TooManyRequestsException`
- Removed `meta.json` in favor of using `pyproject.toml`
- Added Azure Services:
  - `support`
  - `lambda`
  - `sns`
  - `sqs`

## 0.5.2
- Updated to conform with CloudHarvestCoreTasks 0.8.0
- Added the `globa_service` directive

## 0.5.1
- Fixed some reports
- Added `DynamoDB` service

## 0.5.0
- Updated to conform with CloudHarvestCoreTasks 0.7.0
- Added indexes to all existing services
- Added services and reports for the following Azure services:
  - `Route53`
  - `S3`
  - `ServiceQuotas`

## 0.4.1
- Template improvements
- Added
  - `DMS` service
  - `EC2` service

## 0.4.0
- [get_credentials() will check the Azure credentials file for profiles](https://github.com/Cloud-Harvest/CloudHarvestPluginAzure/issues/20)
  - Added the `platforms.azure.credentials_source` configuration option; when `file`, the Azure credentials file will be checked for profiles
  - Added the `platforms.azure.credentials_file` configuration option to specify the path to the Azure credentials file
  - Added the `platforms.azure.<account-number>.alias` configuration option to specify a name for the Azure account when it cannot be retrieved using the `describe_account` API call
  - Added more resiliency when attempting to fetch the account alias as some orgs lock down the `organizations` API service
  - The `Profile` class can now write to the Azure credentials file
  - `get_credentials()` may now check the Azure credentials file for profiles

## 0.3.2
- [Platform configuration needs to allow different role names per account](https://github.com/Cloud-Harvest/CloudHarvestAgent/issues/10)
- Updated to conform with CloudHarvestCoreTasks 0.6.6

## 0.3.1
- Updated to conform with CloudHarvestCoreTasks 0.6.5

## 0.3.0
- Updated to conform with CloudHarvestCoreTasks 0.6.4
- Added reports/services
- Updated reports/services
- Fixed an issue where an Azure account number could be passed as int with an incorrect number of leading zeros

## 0.2.0
- Updated to conform with CloudHarvestCoreTasks 0.6.0
- Updated standard which places all report/service templates into the 'templates' directory
- Imports are now absolute
- Removed the `authenticators` directory and its files to avoid confusion pending future implementation
- Updated the `AzureTask` to accept a true `PSTAR` configuration and self-populate/cache credentials
- Added the `credentials` file which performs `sts-assume-role` operations and caches profile information
- Added some `lightsail` reports/services to the `templates` directory
- Added `tests`

## 0.1.5
- Updated to CloudHarvestCorePluginManager 0.3.1
- Updates to conform to CloudHarvestCoreTasks 4.2

## 0.1.4
- Updates to conform to CloudHarvestCoreTasks 4.0
- Implemented Azure IAM authentication
- `AzureTask` now accepts `credentials`

## 0.1.3
- Update to conform with 
  - CloudHarvestCorePluginManager 0.2.4
  - CloudHarvestCoreTasks 0.3.1
- Added the `services` directory which contains instructions on how to harvest data from Azure
- Added README files for each object category

## 0.1.2
- Updated to conform with CloudHarvestCorePluginManager 0.2.0
- Added this CHANGELOG
