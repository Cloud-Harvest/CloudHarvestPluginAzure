"""
This library provides functions to assume an Azure role and retrieve temporary credentials. It also includes a caching
mechanism to store the credentials for reuse, reducing the need to repeatedly assume the role which can be time-consuming.

Required Azure Permissions:
- sts:AssumeRole
- organizations:DescribeAccount

"""
from logging import getLogger

logger = getLogger('harvest')

class CachedProfiles:
    profiles = {}


class Profile:
    def __init__(self, account_number: str, role_name: str, sourced_from_file: bool = False):
        """
        Initializes a new Profile instance.

        Arguments
        account_number (str): The Azure account number.
        role_name (str): The Azure role name.
        sourced_from_file (bool, optional): Indicates if the profile was sourced from the credentials file. Defaults to False.
        """

        self.account_number = str(account_number).zfill(12)
        self.role_name = role_name
        self.sourced_from_file = sourced_from_file

        # Temporary session credentials
        self.azure_access_key_id = None
        self.azure_secret_access_key = None
        self.azure_session_token = None

        self.account_alias = None
        self.expiration = None
        self.role_arn = None

    @property
    def is_expired(self):
        """
        Check if the profile is expired.
        """
        from datetime import datetime, timezone
        if not self.sourced_from_file:
            return self.expiration < datetime.now(timezone.utc)

        # Credentials sourced from files are not expected to contain expiration information
        else:
            return False

    @property
    def credentials(self) -> dict:
        """
        Returns the credentials for the profile in a format acceptable to the boto3 Session.
        Returns:
            dict: A dictionary containing the Azure credentials.
        """

        return {
            'azure_access_key_id': self.azure_access_key_id,
            'azure_secret_access_key': self.azure_secret_access_key,
            'azure_session_token': self.azure_session_token
        }

    @property
    def name(self) -> str:
        """
        Returns a profile name in the format of account_alias-role_name.
        """

        return f'{str(self.account_alias or self.account_number)}-{str(self.role_name)}'

    def refresh_credentials(self) -> 'Profile':
        """
        Refreshes the credentials for the profile.
        """
        from CloudHarvestPluginAzure.tasks.azure import query_azure

        # Assume the role in the specified account
        response = query_azure(
            service='sts',
            command='assume_role',
            arguments={
                'RoleArn': f'arn:azure:iam::{self.account_number}:role/{self.role_name}',
                'RoleSessionName': 'CloudHarvest'
            },
            region='us-east-1',
        )

        # Extract the temporary credentials from the response
        self.azure_access_key_id = response['AccessKeyId']
        self.azure_secret_access_key = response['SecretAccessKey']
        self.azure_session_token = response['SessionToken']
        self.expiration = response['Expiration']
        self.role_arn = f'arn:azure:iam::{self.account_number}:role/{self.role_name}'

        if self.account_alias is None:
            # If the account alias is not set, try to get it
            self.account_alias = get_account_name(account_number=self.account_number, credentials=self.credentials)

        return self

    def write_to_credentials_file(self, path: str = None):
        """
        Writes the profile to the Azure credentials file.
        """

        from os.path import abspath, exists, expanduser
        from configparser import ConfigParser

        path = abspath(expanduser(path or '~/.azure/credentials'))

        if not exists(path):
            # Create the credentials file and directory if it does not exist
            from pathlib import Path
            Path(path).parent.mkdir(parents=True, exist_ok=True)

            # Touch the file
            Path(path).touch()

        # Read the existing file into a dictionary
        config = ConfigParser()
        config.read(path)

        # Check if the profile already exists
        if not config.has_section(self.name):
            # Create a new section for the profile
            config.add_section(self.name)

        # Write the credentials to the file
        for key, value in self.credentials.items():
            config.set(self.name, key, value)

        # Write the file back to disk
        with open(path, 'w') as configfile:
            config.write(configfile)

        logger.debug(f'wrote {self.name} to {path}')

        return None


def get_profile(account_number: str, role_name: str, force_refresh: bool = False) -> Profile:
    """
    Creates or retrieves a profile for a given Azure account and role. If the profile already exists and is not expired, it will
    be returned. If it is expired, the credentials will be refreshed. If the profile does not exist, a new one will be created.
    This function caches the profiles to avoid repeatedly assuming the role.

    Arguments
    account_number (str): The Azure account number.
    role_name (str): The Azure role name.
    force_refresh (bool): If True, forces a refresh of the credentials even if they are not expired.
    """

    # Make sure incoming account numbers are properly formatted
    account_number = str(account_number).zfill(12)

    # Check if the profile already exists
    if account_number in CachedProfiles.profiles:
        logger.debug(f'Found profile for {account_number} in cache')

        profile = CachedProfiles.profiles[account_number]

        if isinstance(profile, Profile):
            # If the profile is expired, refresh the credentials, unless it was sourced from a file
            if not profile.sourced_from_file and (profile.is_expired or force_refresh):
                profile.refresh_credentials()

    else:
        from CloudHarvestCoreTasks.environment import Environment
        if Environment.get('platforms.azure.credentials_source') == 'file' and account_number:
            # Read the credentials file and return the profile
            CachedProfiles.profiles |= read_credentials_file()
            profile = CachedProfiles.profiles.get(account_number)

        else:
            # Create a new profile and refresh the credentials
            profile = Profile(account_number=account_number, role_name=role_name)
            profile.refresh_credentials()
            CachedProfiles.profiles[account_number] = profile

    return profile


def read_credentials_file(path: str = None) -> dict:
    """
    Reads the Azure credentials file and returns a dictionary of profiles.

    Arguments
        path (str, optional): The path to the Azure credentials file. Defaults to '~/.azure/credentials'.

    Returns
        dict: A dictionary containing the profiles and their corresponding credentials.
    """

    from CloudHarvestCoreTasks.environment import Environment
    from os.path import abspath, exists, expanduser
    path = abspath(expanduser(path or Environment.get('platforms.azure.credentials_file') or '~/.azure/credentials'))

    logger.debug(f'Reading credentials from {path}')

    # Return an empty dictionary if the file does not exist
    if not exists(path):
        return {}

    results = {}

    # Read the credentials file
    from configparser import ConfigParser
    config = ConfigParser()
    config.read(path)

    # Parse the profiles and their credentials
    profiles = {}

    # For each section (profile name), read all the keys and values and set the keys to lower case
    logger.debug(f'Found {len(config.sections())} profiles in {path}')

    for section in config.sections():
        profiles[section] = {
            k.lower(): v
            for k, v in config.items(section)
        }

        # Only attempt to add the profile if it is not already in the cache
        if section != 'default':
            logger.debug(f'Building profile for {section}')

            try:
                credentials = {
                    key: profiles[section].get(key)
                    for key in ('azure_access_key_id', 'azure_secret_access_key', 'azure_session_token')
                }

                logger.debug(f'Retrieving caller identity for {section}')
                from CloudHarvestPluginAzure.tasks.azure import query_azure
                identity = query_azure(
                    service='sts',
                    command='get_caller_identity',
                    arguments={},
                    credentials=credentials,
                    result_path=(
                        'UserId',
                        'Account',
                        'Arn'
                    )
                )

                logger.debug(f'Creating profile for {section}')
                profile = Profile(
                    account_number=identity.get('Account'),
                    role_name=str(identity.get('Arn') or '').split('/', maxsplit=1)[1],    # Sometimes a role will include a / after the account number
                    sourced_from_file=True
                )

                # Continue if the profile is already in the cache. This can happen when multiple jobs are attempting to
                # read the credentials file at the same time.
                if profile.account_number in CachedProfiles.profiles.keys():
                    continue

                profile.account_alias = get_account_name(profile.account_number, credentials)
                profile.azure_access_key_id = credentials.get('azure_access_key_id')
                profile.azure_secret_access_key = credentials.get('azure_secret_access_key')
                profile.azure_session_token = credentials.get('azure_session_token')

                results[profile.account_number] = profile

                logger.debug(f'Created profile {profile.name} for {section}')

            except Exception as e:
                logger.warning(f'Failed to get credentials for {section}: {e}')

    return results


def get_account_name(account_number: str, credentials: dict) -> str or None:
    """
    Looks up the account alias for a given account number. Assumes the account is part of an organization. If it is not,
    or an error is encountered, the provided account number will be returned.

    Arguments
        account_number (str): The Azure account number.
        credentials (dict): The Azure credentials to use for the session. When not provided, boto3 will attempt to use the default credentials.

    Returns
        str or None: The account alias if found, otherwise None.
    """
    from CloudHarvestPluginAzure.tasks.azure import query_azure

    # If an alias is defined in the environment, use that. This is useful for environments where the role cannot access
    # the organization service and the IAM service does not contain a useful alias. Further, some organizations may not
    # want to expose the account name to all users; therefore, a custom alias can be defined in the environment.
    from CloudHarvestCoreTasks.environment import Environment
    result = Environment.get(f'platforms.azure.accounts.{account_number}.alias')

    if result:
        return result

    else:
        logger.debug(f'Failed to get account name for {account_number} using environment. An alias was not defined at `platforms.azure.accounts.{account_number}.alias`')

    # First pass, try the organizations service
    try:
        response = query_azure(
            service='organizations',
            command='describe_account',
            arguments={
                'AccountId': account_number
            },
            credentials=credentials
        )

    except Exception as e:
        logger.debug(f'Failed to get account name for {account_number} using organizations: {e}')

    else:
        return response.get('Name')

    # Second pass, try the IAM service
    try:
        response = query_azure(
            service='iam',
            command='list_account_aliases',
            arguments={},
            credentials=credentials
        )

        if response:
            # If there are multiple aliases, return the first one that does not contain the account number
            for alias in response:
                if account_number not in alias:
                    result = alias
                    break

    except Exception as e:
        logger.debug(f'Failed to get account name for {account_number} using iam: {e}')

    else:
        if result:
            return result

        else:
            logger.debug(f'Failed to get account name for {account_number} using iam because no appropriate alias was found')

    # If no alias is found, return the account number
    return account_number
